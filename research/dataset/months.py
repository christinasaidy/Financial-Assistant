"""Batch 5: named months that already passed this year (decided with Christina on 2026-11-22; PROGRESS.md).

    python -m research.dataset.months --prepare   # plan, seed each user, run every target as the app would
    python -m research.dataset.months --replay    # -> data/batch5/months_{split}.jsonl

Fine-tune 4 read "October" asked on 3 November as last year's October. Every gold answer follows the rule (the most
recent such month), but the mix leans to last year: of the single-month queries, 247 point to last year (the month
has not come yet this year), 154 to this year, and only 34 are the month just before today's.

So already approved questions about one named month and nothing else ("adesh sarafet bi teshreen el awal?": totals,
receipt counts, a category, where the money went, top categories) are asked again by OTHER users whose today makes
that month just passed (mostly the month before today's, some 2-3 months back). The question text is unchanged;
only the user, their day and the year in the SQL change. Sources: batch 2 (reviewed) and batch 1 (English, and
Arabizi the batch-1 audit judged fine); no line with a rejected spelling. Every target runs through the app on the
seeded user (removed after); an empty answer is left out.
"""

import argparse
import json
import random
import re
import tempfile
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.domain.assistant.prompt import UserNames, build_prompt

from research.dataset import build
from research.dataset.answers_build import REJECTED
from research.dataset.rerender import read_prompt
from research.dataset.users import gender_of, remove_user, seed_user
from research.dataset.words import WordsError, _rows, users

RAW_DIR = build.RAW_DIR / "batch5" / "months"
JOBS_FILE = RAW_DIR / "jobs.jsonl"
AUDIT_DIR = build.RAW_DIR / "batch5" / "batch1_audit"
DATA_DIR = build.DATA_DIR / "batch5"
SEED = "fyp-dataset/batch5-months"
TEMPLATES = ("T1", "T2", "T3", "T4", "T5", "T16")  # about the month only (and a category for T3)
BACK = {1: 40, 2: 12, 3: 8}  # how many examples per "months back" (1 = the month just before today's)
_ONE_MONTH = re.compile(r"receipt_date >= '(\d{4})-(\d\d)-01' AND receipt_date < '(\d{4})-(\d\d)-01'")
_ALSO_REJECTED = ("sarfet", "sa7abit", "jaybte", "bekhlas", "man2ish")  # her batch-1 rulings


def _fine_batch1() -> set[str]:
    """Batch-1 Arabizi questions the audit judged fine."""
    fine = set()
    for chunk in AUDIT_DIR.glob("chunk-*.json"):
        verdicts = {v["id"]: v["verdict"] for v in json.loads(chunk.with_name(chunk.name.replace("chunk", "verdict"))
                                                               .read_text(encoding="utf-8"))}  # fmt: skip
        fine |= {c["question"] for c in json.loads(chunk.read_text(encoding="utf-8")) if verdicts.get(c["id"]) == "fine"}
    return fine


def candidates(data_dir: Path = build.DATA_DIR) -> list[dict]:
    fine, found, seen = _fine_batch1(), [], set()
    for source in ("", "batch2/"):
        for split in ("train", "validation"):
            for row in map(json.loads, (data_dir / f"{source}{split}.jsonl").read_text(encoding="utf-8").splitlines()):
                labels, sql = row["labels"], row["messages"][1]["content"]
                one = _ONE_MONTH.findall(sql)
                if labels["template"] not in TEMPLATES or len(one) != 1 or int(one[0][3]) != int(one[0][1]) % 12 + 1:
                    continue
                if re.search(r"\bvendor\b|item_name|brand", sql):  # a shop or item the other user may not have
                    continue
                parts = read_prompt(row["messages"][0]["content"])
                q, language = parts.question, labels["language"]
                bad = [w for w in (*REJECTED, *_ALSO_REJECTED) if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", q, re.I)]
                if parts.history or bad or q in seen or (source == "" and language != "english" and q not in fine):
                    continue
                category = re.search(r"category = '((?:[^']|'')*)'", sql)
                seen.add(q)
                found.append({"source": source or "batch1/", "spec": labels["spec"], "template": labels["template"],
                              "language": language, "question": q, "month": int(one[0][1]), "split": split,
                              "category": category.group(1).replace("''", "'") if category else None, "sql": sql})
    return found


def _target(sql: str, month: int, year: int) -> str:
    end_year, end_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return _ONE_MONTH.sub(f"receipt_date >= '{year}-{month:02d}-01' AND receipt_date < '{end_year}-{end_month:02d}-01'",
                          sql)


def plan(data_dir: Path = build.DATA_DIR) -> list[dict]:
    """Each candidate on a user of its split whose today makes its month `back` months ago, `back` in turn."""
    rng = random.Random(SEED)
    pool = candidates(data_dir)
    rng.shuffle(pool)
    people = [(n, s, d) for n, s, d in users()]
    jobs, used, wanted = [], Counter(), Counter(BACK)
    for c in pool:
        for back in (1, 2, 3):
            if not wanted[back]:
                continue
            fits = [(n, d) for n, s, d in people if s == c["split"] and (d.today.month - back - 1) % 12 + 1 == c["month"]
                    and d.today.month > back and (c["category"] is None or c["category"] in d.categories)
                    and any(r.day.year == d.today.year and r.day.month == c["month"] for r in d.user.receipts)]
            fits = [f for f in fits if used[f[0]] < 3]
            if not fits:
                continue
            number, data = rng.choice(sorted(fits, key=lambda f: f[0]))
            used[number] += 1
            wanted[back] -= 1
            jobs.append({"job_id": f"m-{len(jobs)}", "user": number, "split": c["split"], "back": back,
                         "today": data.today.isoformat(), "from_spec": c["spec"], "template": c["template"],
                         "language": c["language"], "question": c["question"],
                         "target": _target(c["sql"], c["month"], data.today.year)})
            break
    return jobs


def prepare(jobs_file: Path = JOBS_FILE) -> list[dict]:
    jobs = plan()
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    data = {n: d for n, _, d in users()}
    for number in sorted({j["user"] for j in jobs}):
        user = data[number].user
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                for job in (j for j in jobs if j["user"] == number):
                    job["names"] = asdict(names)
                    job["rows"] = _rows(services.assistant.run_query(user_id, rules.prepare(
                        guard.check(job["target"]), names, user.today)))  # fmt: skip
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs), encoding="utf-8")
    return jobs


def replay(jobs_file: Path = JOBS_FILE, out_dir: Path = DATA_DIR) -> dict:
    jobs = [json.loads(line) for line in jobs_file.read_text(encoding="utf-8").splitlines()]
    keep = ("job_id", "user", "question", "target")
    if [{k: j[k] for k in keep} for j in jobs] != [{k: j[k] for k in keep} for j in plan()]:
        raise WordsError("the saved jobs are not the plan: prepare again")
    out, empty = {"train": [], "validation": []}, 0
    for job in jobs:
        if not job["rows"]:  # nothing bought in that month after all: left out, as decided
            empty += 1
            continue
        prompt = build_prompt(job["question"], UserNames(**job["names"]), date.fromisoformat(job["today"]), (),
                              gender=gender_of(job["user"]))  # fmt: skip
        labels = {"template": job["template"], "kind": "sql", "language": job["language"], "user": job["user"],
                  "split": job["split"], "spec": job["job_id"], "result_rows": job["rows"], "part": "months",
                  "months_back": job["back"], "from_spec": job["from_spec"]}  # fmt: skip
        out[job["split"]].append({"messages": [{"role": "user", "content": prompt},
                                               {"role": "assistant", "content": job["target"]}], "labels": labels})
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in out.items():
        (out_dir / f"months_{split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                       encoding="utf-8")  # fmt: skip
    return {"train": len(out["train"]), "validation": len(out["validation"]), "empty, left out": empty,
            "back": dict(Counter(j["back"] for j in jobs if j["rows"]))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for flag in ("--plan", "--prepare", "--replay"):
        mode.add_argument(flag, action="store_true")
    args = parser.parse_args(argv)
    if args.plan:
        jobs = plan()
        print(len(jobs), "jobs:", dict(Counter((j["split"], j["back"]) for j in jobs)))
        for j in jobs[:8]:
            print(" ", j["user"], j["today"], "|", j["question"], "|", re.findall(r"'\d{4}-\d\d-01'", j["target"]))
    elif args.prepare:
        saved = prepare()
        print(len(saved), "jobs; empty:", sum(1 for j in saved if not j["rows"]))
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
