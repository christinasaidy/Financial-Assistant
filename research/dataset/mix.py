"""The training mix and its coverage check (approved by the user on 2026-11-15).

    python -m research.dataset.mix          # builds data/mix/{train,validation}.jsonl, or refuses with what is missing

The batch-2 mix kept only batch 1's English, so batch 1's Arabizi (and its "li ata3", "sarle", "bel miyye", "bala ma"
and most clarifying questions) never reached training. Now every batch is taken whole, and the mix is refused unless
the Arabizi and mixed questions of the training split meet the approved thresholds:

- CLARIFY + UNSUPPORTED are at least 15% of them;
- each approved expression appears at least 20 times;
- totals, shop totals, top shop and receipt counts each have at least 5 for this month, last month and yesterday;
- at least 40% of the per-100 g/ml shop comparisons do not say "100" (batch 2: all 75 did, a wording shortcut).

Since batch 5 (2026-11-18) every line is first rebuilt with today's prompt (research/dataset/rerender.py): the user's
gender, the new chat rule, and the assistant's replies in the form for that gender. A reply with no approved forms or
a prompt that cannot be read back refuses the whole mix. Then earlier exchanges are put in front of some questions
(research/dataset/history.py), and the mix is refused unless 65-75% of the chats ignore their history.
"""

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

from research.dataset.genders import UnformedReply
from research.dataset.history import HistoryError, add_history, history_report
from research.dataset.rerender import UnreadablePrompt, read_prompt, rerender

DATA_DIR = Path(__file__).parent / "data"
SPLITS = ("train", "validation")
SOURCES = ("{split}.jsonl", "batch2/{split}.jsonl", "batch2/extras_{split}.jsonl", "batch3/{split}.jsonl",
           "batch4/{split}.jsonl", "batch5/{split}.jsonl")  # batch 5's chats since 2026-11-19
SEED = "fyp-dataset/mix-batch4"

BOUNDARY_SHARE = 0.15
EXPRESSION_LEAST = 20
COMMON_LEAST = 5
IMPLICIT_SHARE = 0.40
EXPRESSIONS = {
    "last month (li ata3, ekher shaher, el shaher el madi ...)":
        r"li ata3|ekher shaher|shah(e)?r el madi|el ablo|li mara2|li mar2|el shaher el mara2",
    "sarle (so far)": r"\bsar ?l[ei]\b",
    "la halla2 (until now)": r"\bla ?hall?a2\b|\bla halae\b",
    "percent (bel miyye, nesbe, %)": r"bel miy+e|bil miy+e|bl miy+e|%|\bnesb[ei]",
    "negation (bala ma, ma t2elle)": r"\bbala ma\b|\bma t2el+e\b|\bma t2olle\b",
    "since a weekday (men nhar el tanayn ...)":
        r"\b(men|mn|bayn|beyn) (nhar )?(el )?(tanayn|tanain|taleta|erb3a|khamis|jem3a|sabet|a7ad)\b",
    "yesterday (mbere7, mberha)": r"\bmber(e7|eh|ha|i7)\b|\bembere7\b",
    "usually (3adatan, bel 3ade)": r"3adatan|aadatan|\bb(e)?l (3|a)ade\b",
}
COMMON = {"T1": "total", "T6": "shop total", "T7": "top shop", "T16": "receipt count"}
COMMON_PERIODS = ("this_month", "last_month", "yesterday")
PER_100 = "IN ('g', 'ml')"

# Batch 4's minimums (approved 2026-11-16): the user's spellings, and the new kinds of question. Each is
# (pattern in the question, least, an optional template the row must have, an optional text its answer must contain).
AS_COUNT = r"\b(aday|adday|adde|adaysh|addesh|adesh|2adesh)\b"
BATCH4_MINIMUMS = {
    "jebet": (r"\bjebet\b", 40, None, None),
    "shtrit": (r"\bshtrit\b", 40, None, None),
    "aal": (r"\baal\b", 60, None, None),
    "aa": (r"\baa\b", 40, None, None),
    "shefle": (r"\bshefle\b", 30, None, None),
    "aday as a count": (AS_COUNT, 30, "T15", "SUM(quantity)"),
    "bi aday (the price)": (r"\bb(i)? ?(aday|adde|adesh|adaysh)\b", 15, None, None),
    "the last time": (r".", 30, "B11", "MAX(receipt_date)"),
}


class CoverageError(ValueError):
    pass


def _question(row: dict) -> str:
    return row["messages"][0]["content"].rsplit("Question: ", 1)[-1].lower()


def coverage(rows: list[dict]) -> dict:
    """What the Arabizi and mixed questions cover (English is plentiful and is not counted)."""
    arabizi = [r for r in rows if r["labels"]["language"] in ("arabizi", "mixed")]
    kinds = Counter(r["labels"]["kind"] for r in arabizi)
    expressions = {name: sum(1 for r in arabizi if re.search(pattern, _question(r)))
                   for name, pattern in EXPRESSIONS.items()}  # fmt: skip
    common = {(t, p): sum(1 for r in arabizi if r["labels"]["template"] == t and r["labels"].get("period") == p)
              for t in COMMON for p in COMMON_PERIODS}  # fmt: skip
    per_100 = [r for r in arabizi if r["labels"]["kind"] == "sql" and PER_100 in r["messages"][1]["content"]
               and "vendor" in r["messages"][1]["content"]]  # fmt: skip
    batch4 = {name: sum(1 for r in arabizi if re.search(pattern, _question(r))
                        and (template is None or r["labels"]["template"] == template)
                        and (answer is None or answer in r["messages"][1]["content"]))
              for name, (pattern, _, template, answer) in BATCH4_MINIMUMS.items()}  # fmt: skip
    return {"arabizi": len(arabizi), "kinds": dict(kinds), "expressions": expressions, "common": common,
            "per_100": len(per_100), "per_100_implicit": sum(1 for r in per_100 if "100" not in _question(r)),
            "batch4": batch4}


def failures(report: dict) -> list[str]:
    found = []
    boundary = report["kinds"].get("clarify", 0) + report["kinds"].get("unsupported", 0)
    if boundary < BOUNDARY_SHARE * report["arabizi"]:
        found.append(f"CLARIFY + UNSUPPORTED: {boundary / max(1, report['arabizi']):.1%} < {BOUNDARY_SHARE:.0%}")
    found += [f"{name}: {n} < {EXPRESSION_LEAST}" for name, n in report["expressions"].items() if n < EXPRESSION_LEAST]
    found += [f"{t} ({COMMON[t]}) for {p}: {n} < {COMMON_LEAST}" for (t, p), n in report["common"].items()
              if n < COMMON_LEAST]  # fmt: skip
    if report["per_100"] and report["per_100_implicit"] < IMPLICIT_SHARE * report["per_100"]:
        found.append(f"per-100 comparisons that do not say 100: {report['per_100_implicit']}/{report['per_100']} "
                     f"< {IMPLICIT_SHARE:.0%}")
    return found


def batch4_failures(report: dict) -> list[str]:
    return [f"{name}: {n} < {BATCH4_MINIMUMS[name][1]}" for name, n in report["batch4"].items()
            if n < BATCH4_MINIMUMS[name][1]]  # fmt: skip


# Batch 5 part 1's minimums for the training chats (approved by Christina, decision 11, 2026-11-17, plus her
# follow-up-looking topic changes).
PART1_MINIMUMS = {
    "topic changes": 300,  # chats whose new question ignores the history
    "after a CLARIFY, UNSUPPORTED or REPLY": 150,
    "3 or more earlier exchanges": 150,
    "follow-ups after older turns": 150,
    "answered CLARIFYs": 100,
    "thanks or ma fhemet with history": 60,
    "follow-up-looking topic changes": 60,
}


def part1_report(rows: list[dict]) -> dict[str, int]:
    chats = [r for r in rows if r["labels"].get("history") or r["labels"]["kind"] == "follow_up"]
    earlier = {id(r): read_prompt(r["messages"][0]["content"]).history for r in chats}
    return {
        "topic changes": sum(r["labels"].get("history_role") == "independent" and r["labels"]["kind"] == "sql"
                             for r in chats),
        "after a CLARIFY, UNSUPPORTED or REPLY": sum(
            any(e.reply.startswith(("CLARIFY:", "UNSUPPORTED", "REPLY:")) for e in earlier[id(r)]) for r in chats),
        "3 or more earlier exchanges": sum(r["labels"].get("history", 1) >= 3 for r in chats),
        "follow-ups after older turns": sum(r["labels"].get("history_role") == "dependent"
                                            and r["labels"].get("history", 1) >= 2 for r in chats),
        "answered CLARIFYs": sum(r["labels"]["template"] == "P1B" for r in chats),
        "thanks or ma fhemet with history": sum(r["labels"]["template"] in ("R2", "C6")
                                                or r["labels"].get("carried") == "accepted" for r in chats),
        "follow-up-looking topic changes": sum(r["labels"]["template"] == "P1A" for r in chats),
    }  # fmt: skip


def part1_failures(report: dict[str, int]) -> list[str]:
    return [f"{name}: {report[name]} < {least}" for name, least in PART1_MINIMUMS.items() if report[name] < least]


def build_mix(data_dir: Path = DATA_DIR, out_dir: Path | None = None) -> dict[str, int]:
    """Every batch, whole, shuffled with a fixed seed. Refuses (CoverageError) before writing anything if the
    training split misses a threshold."""
    out_dir = out_dir or data_dir / "mix"
    splits = {}
    for split in SPLITS:
        lines = []
        for source in SOURCES:
            path = data_dir / source.format(split=split)
            lines += [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        random.Random(f"{SEED}/{split}").shuffle(lines)
        rebuilt, _ = add_history([rerender(json.loads(line)) for line in lines], split)
        splits[split] = [json.dumps(row, ensure_ascii=False) for row in rebuilt]
    report = coverage([json.loads(line) for line in splits["train"]])
    missing = failures(report) + batch4_failures(report)
    if any(r.get("labels", {}).get("template", "").startswith("P1") for r in map(json.loads, splits["train"])):
        missing += part1_failures(part1_report([json.loads(line) for line in splits["train"]]))
    if missing:
        raise CoverageError("; ".join(missing))
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, lines in splits.items():
        (out_dir / f"{split}.jsonl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return {split: len(lines) for split, lines in splits.items()}


def main() -> int:
    try:
        counts = build_mix()
    except CoverageError as exc:
        print("REFUSED, the training mix misses:", *str(exc).split("; "), sep="\n  ")
        return 1
    except (UnformedReply, UnreadablePrompt) as exc:
        print("REFUSED, a line cannot be rebuilt with today's prompt:", exc)
        return 1
    except HistoryError as exc:
        print("REFUSED, the chats are not balanced:", exc)
        return 1
    train = [json.loads(line) for line in (DATA_DIR / "mix" / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    report = coverage(train)
    print("mix:", counts, "| languages:", dict(Counter(r["labels"]["language"] for r in train)))
    print(f"Arabizi + mixed: {report['arabizi']}, kinds {report['kinds']}")
    for name, n in report["expressions"].items():
        print(f"  {n:5d}  {name}")
    print(f"  per-100 comparisons not saying 100: {report['per_100_implicit']}/{report['per_100']}")
    print("  common questions x periods:", {f"{t}/{p}": n for (t, p), n in report["common"].items()})
    print("  batch 4:", report["batch4"])
    print("  part 1:", part1_report(train))
    for split in SPLITS:
        rows = [json.loads(line) for line in (DATA_DIR / "mix" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]
        print(f"  history ({split}):", history_report(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
