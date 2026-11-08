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
