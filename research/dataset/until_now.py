"""Batch 5 part 6: "la hadit hala2" (until now), her form (decided with Christina on 2026-11-22; PROGRESS.md).

    python -m research.dataset.until_now    # -> data/batch5/until_now_{split}.jsonl

Her ruling: "sarli defe3 ... la hala2" is right, and "la hadit hala2" is said too (a few "la hadit halla2" are fine).
No stored question says it. So 20 already approved questions that say "la hala2 / la halla2" once (batches 2-4 and
part 4's kinds; one question, no chat; Arabizi or mixed; the approved question fixes applied first, so none says
sarfet) are asked again with only that phrase changed: every 5th as "la hadit halla2", the rest "la hadit hala2". The
user, their day and the answer are the stored ones. The sarle / sar / seret questions come first.
"""

import argparse
import copy
import json
import random
import re
from pathlib import Path

from research.dataset import build
from research.dataset.answers_build import REJECTED
from research.dataset.fixes import fixed_question
from research.dataset.rerender import read_prompt

DATA_DIR = build.DATA_DIR / "batch5"
SEED = "fyp-dataset/batch5-until-now"
SOURCES = ("batch2/train.jsonl", "batch3/train.jsonl", "batch4/train.jsonl", "batch5/kinds_train.jsonl")
COUNT, HALLA2_EVERY = 20, 5
UNTIL_NOW = re.compile(r"(?<!\w)la ?hal+a2(?!\w)", re.IGNORECASE)
SARLE = re.compile(r"(?<!\w)(sar|sarle|sarli|seret|sert|serit)(?!\w)", re.IGNORECASE)  # not sarafet


def candidates(data_dir: Path = build.DATA_DIR) -> list[dict]:
    found, seen = [], set()
    for source in SOURCES:
        for line in (data_dir / source).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            labels = row["labels"]
            if labels["kind"] != "sql" or labels["language"] == "english":
                continue
            parts = read_prompt(row["messages"][0]["content"])
            question = fixed_question(parts.question)
            if parts.history or len(UNTIL_NOW.findall(question)) != 1 or question in seen:
                continue
            if any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", question, re.IGNORECASE) for w in REJECTED):
                continue
            seen.add(question)
            found.append({"source": source, "row": row, "stored": parts.question, "question": question})
    return found


def chosen(data_dir: Path = build.DATA_DIR) -> list[dict]:
    pool = candidates(data_dir)
    random.Random(SEED).shuffle(pool)
    first = [c for c in pool if SARLE.search(c["question"])]
    return (first + [c for c in pool if c not in first])[:COUNT]


def examples(data_dir: Path = build.DATA_DIR) -> list[dict]:
    held_out = build.test_questions(None)
    from research.dataset.checks import near_duplicate  # noqa: PLC0415

    out = []
    for index, c in enumerate(chosen(data_dir)):
        phrase = "la hadit halla2" if index % HALLA2_EVERY == HALLA2_EVERY - 1 else "la hadit hala2"
        question = UNTIL_NOW.sub(phrase, c["question"])
        if near_duplicate(question, held_out):
            continue
        row = copy.deepcopy(c["row"])
        old = f"Question: {c['stored']}\nReply:"
        prompt = row["messages"][0]["content"]
        if prompt.count(old) != 1:
            raise ValueError(f"the stored question is not where expected: {c['stored']!r}")
        row["messages"][0]["content"] = prompt.replace(old, f"Question: {question}\nReply:")
        row["labels"] = {**row["labels"], "part": "until_now", "from_spec": row["labels"]["spec"],
                         "spec": f"h-{index}", "split": "train"}  # fmt: skip
        out.append(row)
    return out


def build_files(data_dir: Path = build.DATA_DIR, out_dir: Path = DATA_DIR) -> dict:
    rows = examples(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "until_now_train.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                   encoding="utf-8")  # fmt: skip
    (out_dir / "until_now_validation.jsonl").write_text("", encoding="utf-8")
    return {"train": len(rows), "halla2": sum("la hadit halla2" in r["messages"][0]["content"] for r in rows),
            "candidates": len(candidates(data_dir))}


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(build_files())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
