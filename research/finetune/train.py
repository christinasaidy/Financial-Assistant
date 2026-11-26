"""LoRA fine-tuning of the small model on the dataset, on a RunPod GPU (decided with the user on 2026-11-08).

    python train.py --data /workspace/data --out /root/ft-4b              # the real run
    python train.py --data /workspace/data --out /root/ft-test --max-steps 5   # a quick check that it all works
    python train.py --data /workspace/data --out /root/x --lengths-only        # only the token lengths, no GPU

Every example is tokenized before the model is loaded; the run prints the longest in real tokens and stops if any
is over --max-length (6,144 since batch 5, 2026-11-17), naming all of them. A check run (--max-steps) trains on the
longest examples, so it needs as much memory as the hardest batches of the real run.

Only the language part of Qwen3.5 is trained (it is served with --language-model-only); the vision part is kept as
it is, so the merged model has exactly the base model's shape and vLLM serves it the same way. Each example is the
chat text vLLM builds for the app's prompt with thinking off, then the reply; only the reply is learned. At the end
the adapter is saved on its own and also merged into a full model in --out, ready for serve.sh.
"""

import argparse
import json
import random
import sys
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForImageTextToText, AutoProcessor, AutoTokenizer, Trainer, TrainingArguments

try:
    from research.finetune.examples import (MAX_LENGTH, TooLong, checkpoint_settings, encode_all, latest_checkpoint,
                                            longest_first, pad, read_pairs)  # fmt: skip
except ImportError:  # on the pod the files sit side by side
    sys.path.insert(0, str(Path(__file__).parent))
    from examples import (MAX_LENGTH, TooLong, checkpoint_settings, encode_all, latest_checkpoint, longest_first, pad,
                          read_pairs)  # fmt: skip

SEED = 20261108
LINEAR_SKIP = ("visual", "vision", "lm_head", "embed")  # never adapt these


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--data", type=Path, required=True, help="the folder with train.jsonl and validation.jsonl")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=float, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--accumulate", type=int, default=8, help="batches per update (16 examples per update)")
    parser.add_argument("--max-length", type=int, default=MAX_LENGTH)
    parser.add_argument("--max-steps", type=int, default=-1, help="stop early, for a quick check")
    parser.add_argument("--lengths-only", action="store_true", help="print the token lengths and stop")
    args = parser.parse_args()
    random.seed(SEED)
    torch.manual_seed(SEED)

    tokenizer = AutoTokenizer.from_pretrained(args.base)

    def prefix(prompt: str) -> str:  # exactly what vLLM sends the model for the app's prompt, thinking off
        return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False,
                                             add_generation_prompt=True, enable_thinking=False)

    def tokenize(text: str) -> list[int]:
        return tokenizer(text, add_special_tokens=False)["input_ids"]

    splits, longest = {}, 0
    for name in ("train", "validation"):
        pairs = read_pairs(args.data / f"{name}.jsonl")
        try:
            found = encode_all(pairs, prefix, tokenize, args.max_length)
        except TooLong as exc:
            print(f"STOPPED before loading the model: {name}: {exc}", flush=True)
            return 1
        question = pairs[found.longest_index].prompt.rsplit("Question: ", 1)[-1].removesuffix("\nReply:")
        print(f"{name}: {len(pairs)} examples, longest {found.longest} tokens (line {found.longest_index + 1}, "
              f"{args.max_length} allowed): {question[:80]}", flush=True)  # fmt: skip
        splits[name], longest = found.examples, max(longest, found.longest)
    if args.lengths_only:
        return 0
    print("first example as the model sees it:\n" + tokenizer.decode(splits["train"][0]["input_ids"])[-700:], flush=True)
    if args.max_steps >= 0:  # a check run: its batches are the longest ones
        splits["train"] = longest_first(splits["train"], args.max_steps * args.batch * args.accumulate)
        print(f"check run: training on the {len(splits['train'])} longest examples", flush=True)

    model = AutoModelForImageTextToText.from_pretrained(args.base, dtype=torch.bfloat16, device_map="cuda")
    model.config.use_cache = False
    targets = sorted({name.rsplit(".", 1)[-1] for name, module in model.named_modules()
                      if isinstance(module, torch.nn.Linear) and not any(s in name for s in LINEAR_SKIP)})
    print("LoRA on:", targets, flush=True)
    config = LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05, target_modules=targets,
                        exclude_modules=r".*(visual|vision).*", task_type="CAUSAL_LM")  # fmt: skip
    model = get_peft_model(model, config)
    model.print_trainable_parameters()
    model.enable_input_require_grads()

    class Rows(torch.utils.data.Dataset):
        def __init__(self, rows: list[dict]) -> None:
            self.rows = rows

        def __len__(self) -> int:
            return len(self.rows)

        def __getitem__(self, index: int) -> dict:
            return self.rows[index]

    def collate(batch: list[dict]) -> dict:
        return {key: torch.tensor(value) for key, value in pad(batch, tokenizer.pad_token_id).items()}

    training = TrainingArguments(
        output_dir=str(args.out / "checkpoints"), num_train_epochs=args.epochs, max_steps=args.max_steps,
        per_device_train_batch_size=args.batch, per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.accumulate, learning_rate=args.lr, lr_scheduler_type="cosine",
        warmup_steps=10, weight_decay=0.0, bf16=True, gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False}, logging_steps=10, eval_strategy="epoch"
        if args.max_steps < 0 else "no", report_to="none", remove_unused_columns=False, **checkpoint_settings(args.max_steps),
        seed=SEED, data_seed=SEED,
    )  # fmt: skip
    trainer = Trainer(model=model, args=training, train_dataset=Rows(splits["train"]),
                      eval_dataset=Rows(splits["validation"]), data_collator=collate)  # fmt: skip
    resume = latest_checkpoint(args.out / "checkpoints")  # a run cut off part way carries on from its last save
    if resume:
        print("resuming from", resume, flush=True)
    trainer.train(resume_from_checkpoint=resume)
    final = trainer.evaluate() if args.max_steps < 0 else {}
    print("validation:", final, flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out / "adapter")
    merged = model.merge_and_unload()
    merged.config.use_cache = True
    merged.save_pretrained(args.out, safe_serialization=True)
    tokenizer.save_pretrained(args.out)
    AutoProcessor.from_pretrained(args.base).save_pretrained(args.out)
    (args.out / "training.json").write_text(json.dumps({
        "base": args.base, "epochs": args.epochs, "lr": args.lr, "rank": args.rank, "batch": args.batch,
        "accumulate": args.accumulate, "max_steps": args.max_steps, "seed": SEED, "train": len(splits["train"]),
        "validation": len(splits["validation"]), "longest_tokens": longest, "log": trainer.state.log_history,
    }, indent=2))  # fmt: skip
    print(f"Merged model saved in {args.out}; serve it with: bash serve.sh {args.out} --language-model-only", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
