"""Turning the dataset's chat examples into what LoRA training needs (no ML libraries, so it is tested anywhere).

Each example becomes the exact text the model sees when the app asks it a question (the chat template with thinking
off, as vLLM builds it) followed by the reply it should give. Only the reply is learned: the prompt's tokens are
masked out of the loss.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

IGNORE = -100  # the label that tells the loss to skip a token
END = "<|im_end|>"  # Qwen ends every reply with it; the model must learn to stop


@dataclass(frozen=True)
class Pair:
    prompt: str  # the app's own prompt (build_prompt), as the user message
    reply: str  # the SQL, or CLARIFY: / REPLY: / UNSUPPORTED


def read_pairs(path: Path) -> list[Pair]:
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        user, assistant = json.loads(line)["messages"]
        if user["role"] != "user" or assistant["role"] != "assistant":
            raise ValueError(f"Expected a user message then an assistant reply: {line[:80]}")
        pairs.append(Pair(user["content"], assistant["content"]))
    return pairs


def encode(pair: Pair, prefix: Callable[[str], str], tokenize: Callable[[str], list[int]], max_length: int) -> dict:
    """Token ids and labels for one example. `prefix` turns the prompt into the chat text up to where the reply
    starts; the reply's tokens (and the end token) are the only labels. Too long is an error, never cut silently."""
    prompt_ids = tokenize(prefix(pair.prompt))
    reply_ids = tokenize(pair.reply + END)
    if len(prompt_ids) + len(reply_ids) > max_length:
        raise ValueError(f"An example has {len(prompt_ids) + len(reply_ids)} tokens, more than {max_length}")
    return {"input_ids": prompt_ids + reply_ids, "labels": [IGNORE] * len(prompt_ids) + reply_ids}


MAX_LENGTH = 6144  # tokens; batch 5 chats carry up to 6 earlier exchanges (changed requirement, 2026-11-17)


class TooLong(ValueError):
    """Examples over the length limit, all of them listed, found before the model is loaded."""


@dataclass(frozen=True)
class Lengths:
    examples: list[dict]
    longest: int
    longest_index: int  # position in the file, so the example can be found


def encode_all(pairs: list[Pair], prefix: Callable[[str], str], tokenize: Callable[[str], list[int]],
               max_length: int) -> Lengths:  # fmt: skip
    """Every example encoded, and the longest one. Raises TooLong naming every example over the limit (not only the
    first), so one look at the check run shows all that must be fixed."""
    examples, over = [], []
    for index, pair in enumerate(pairs):
        prompt_ids, reply_ids = tokenize(prefix(pair.prompt)), tokenize(pair.reply + END)
        length = len(prompt_ids) + len(reply_ids)
        if length > max_length:
            over.append((index, length))
        examples.append({"input_ids": prompt_ids + reply_ids, "labels": [IGNORE] * len(prompt_ids) + reply_ids})
    if over:
        shown = ", ".join(f"line {index + 1} ({length} tokens)" for index, length in over[:20])
        raise TooLong(f"{len(over)} examples have more than {max_length} tokens: {shown}")
    lengths = [len(e["input_ids"]) for e in examples]
    longest = max(range(len(lengths)), key=lengths.__getitem__) if lengths else -1
    return Lengths(examples, lengths[longest] if lengths else 0, longest)


def longest_first(examples: list[dict], count: int) -> list[dict]:
    """The `count` longest examples, longest first: what a short check run trains on, so that it uses as much GPU
    memory as the hardest batches of the real run will."""
    return sorted(examples, key=lambda e: len(e["input_ids"]), reverse=True)[:count]


def pad(batch: list[dict], pad_id: int) -> dict:
    """Pad a batch on the right: padding is masked from attention and from the loss."""
    longest = max(len(example["input_ids"]) for example in batch)
    padded = {"input_ids": [], "labels": [], "attention_mask": []}
    for example in batch:
        missing = longest - len(example["input_ids"])
        padded["input_ids"].append(example["input_ids"] + [pad_id] * missing)
        padded["labels"].append(example["labels"] + [IGNORE] * missing)
        padded["attention_mask"].append([1] * len(example["input_ids"]) + [0] * missing)
    return padded


CHECKPOINT_EVERY = 100  # steps; about 30 minutes, the most a crash or a dropped terminal can now cost (2026-11-15)


def checkpoint_settings(max_steps: int) -> dict:
    """A real run saves every 100 steps and keeps the last two; a short check run (max_steps >= 0) saves nothing."""
    if max_steps >= 0:
        return {"save_strategy": "no"}
    return {"save_strategy": "steps", "save_steps": CHECKPOINT_EVERY, "save_total_limit": 2}


def latest_checkpoint(folder: Path) -> str | None:
    """The newest checkpoint-<step> folder to resume from, by step number, or None to start from the beginning."""
    found = [p for p in folder.glob("checkpoint-*") if p.name.split("-", 1)[1].isdigit()] if folder.is_dir() else []
    return str(max(found, key=lambda p: int(p.name.split("-", 1)[1]))) if found else None
