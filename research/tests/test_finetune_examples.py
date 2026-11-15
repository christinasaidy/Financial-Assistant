"""The fine-tuning data preparation: only the reply is learned, nothing is cut, padding is ignored."""

import json

import pytest

from research.finetune.examples import END, IGNORE, Pair, encode, pad, read_pairs


def tokenize(text: str) -> list[int]:  # one token per character: enough to check the masking
    return [ord(ch) for ch in text]


def prefix(prompt: str) -> str:
    return f"<user>{prompt}<assistant>"


def test_only_the_reply_and_its_end_token_are_learned():
    encoded = encode(Pair("Q", "SELECT 1"), prefix, tokenize, 100)
    prompt_length = len("<user>Q<assistant>")
    assert encoded["input_ids"] == tokenize("<user>Q<assistant>SELECT 1" + END)
    assert encoded["labels"][:prompt_length] == [IGNORE] * prompt_length
    assert encoded["labels"][prompt_length:] == tokenize("SELECT 1" + END)


def test_an_example_that_is_too_long_is_an_error_not_cut():
    with pytest.raises(ValueError, match="more than 20"):
        encode(Pair("a long question", "SELECT 1"), prefix, tokenize, 20)


def test_padding_is_masked_from_attention_and_loss():
    batch = pad([{"input_ids": [5, 6, 7], "labels": [IGNORE, 6, 7]}, {"input_ids": [8], "labels": [8]}], pad_id=0)
    assert batch["input_ids"] == [[5, 6, 7], [8, 0, 0]]
    assert batch["labels"] == [[IGNORE, 6, 7], [8, IGNORE, IGNORE]]
    assert batch["attention_mask"] == [[1, 1, 1], [1, 0, 0]]


def test_the_dataset_files_are_read_as_prompt_and_reply(tmp_path):
    path = tmp_path / "train.jsonl"
    path.write_text(json.dumps({"messages": [{"role": "user", "content": "p"},
                                             {"role": "assistant", "content": "SELECT 1"}], "labels": {}}) + "\n")
    assert read_pairs(path) == [Pair("p", "SELECT 1")]
    path.write_text(json.dumps({"messages": [{"role": "assistant", "content": "x"},
                                             {"role": "user", "content": "y"}]}) + "\n")
    with pytest.raises(ValueError):
        read_pairs(path)


# --- checkpoints (approved 2026-11-15: a dropped browser terminal cost 2 hours of a run that saved nothing) ---

from research.finetune.examples import checkpoint_settings, latest_checkpoint  # noqa: E402


def test_a_real_run_saves_every_100_steps_and_keeps_the_last_two():
    assert checkpoint_settings(-1) == {"save_strategy": "steps", "save_steps": 100, "save_total_limit": 2}


def test_a_short_check_run_saves_nothing():
    assert checkpoint_settings(5) == {"save_strategy": "no"}


def test_a_run_resumes_from_its_latest_checkpoint_by_step_number(tmp_path):
    assert latest_checkpoint(tmp_path / "checkpoints") is None
    for step in (900, 1000, 100):
        (tmp_path / "checkpoints" / f"checkpoint-{step}").mkdir(parents=True)
    assert latest_checkpoint(tmp_path / "checkpoints") == str(tmp_path / "checkpoints" / "checkpoint-1000")
