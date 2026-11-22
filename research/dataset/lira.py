"""Batch 5: amounts in lira (her rulings, 2026-11-23; PROGRESS.md "lira").

    python -m research.dataset.lira --prepare   # seed each user, run every target as the app would -> jobs.jsonl
    python -m research.dataset.lira --replay    # -> data/batch5/lira_{split}.jsonl

Her ruling: "bel lira" works like "bel dollar": every amount converted at its receipt's saved rate (the views'
total_lbp, migration 0009), returning only the LBP value; "the receipts I paid in lira" (li dafa3to bel lira) are
only the receipts with currency 'LBP'. Spellings: bel lira, bl lira (her "dnt forget bl"), bel LBP, bel lebnene.

All from her approved lines (batches 2-4), on their own users and days:
- LI1: the 13 approved "bel dollar" totals (T2) with the currency word changed, SUM(total_usd) -> SUM(total_lbp);
- LI2: approved plain totals (T1, no shop) with "bel lira" before the end, the same total in LBP only;
- LI3: approved plain totals with ", bas li dafa3to bel lira": the LBP receipts only (new wording: flagged for her).
No line with a rejected spelling. Every target runs through the app on the seeded user (removed after); an empty
answer is left out, as in every part.
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
from research.dataset.rerender import UnreadablePrompt, read_prompt
from research.dataset.users import gender_of, remove_user, seed_user
from research.dataset.words import _rows, users

RAW_DIR = build.RAW_DIR / "batch5" / "lira"
JOBS_FILE = RAW_DIR / "jobs.jsonl"
DATA_DIR = build.DATA_DIR / "batch5"
SEED = "fyp-dataset/batch5-lira"
SPELLINGS = ("bel lira", "bl lira", "bel LBP", "bl lira", "bel lebnene")  # bl twice: her reminder
WANT = {"LI2": 15, "LI3": 15}
_DOLLAR = re.compile(r"(?<!\w)(bel|bl|bi) (dollar|usd)(?!\w)", re.IGNORECASE)
_T2 = re.compile(r"^SELECT SUM\(total_usd\) AS total_spent_usd FROM receipts WHERE (?P<where>.+)$")
_T1 = re.compile(r"^SELECT currency, SUM\(total\) AS total_spent, SUM\(total_usd\) AS total_spent_usd FROM receipts "
                 r"WHERE (?P<where>.+) GROUP BY currency$")  # fmt: skip


def _rejected(question: str) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", question, re.IGNORECASE) for w in REJECTED)


def _approved() -> list[dict]:
    found = []
    for source in ("batch2", "batch3", "batch4"):
        for split in ("train", "validation"):
            for line in (build.DATA_DIR / source / f"{split}.jsonl").read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                labels = row["labels"]
                if labels["kind"] != "sql" or labels["language"] == "english" or labels["template"] not in ("T1", "T2"):
                    continue
                try:
                    parts = read_prompt(row["messages"][0]["content"])
                except UnreadablePrompt:
                    continue
                if parts.history or _rejected(parts.question):
                    continue
                found.append({"question": parts.question, "sql": row["messages"][1]["content"], "split": split,
                              "names": asdict(parts.names), "today": parts.today.isoformat(), "user": labels["user"],
                              "template": labels["template"], "language": labels["language"],
                              "spec": labels.get("spec")})  # fmt: skip
    return found


def _with_word(question: str, word: str) -> str:
    """The question with the lira word before its end ("aday sarafet hal shaher bel lira?")."""
    q = question.rstrip()
    return f"{q[:-1].rstrip()} {word}?" if q.endswith("?") else f"{q} {word}"


def plan() -> list[dict]:
    rng = random.Random(SEED)
    approved = _approved()
    jobs = []
    for index, a in enumerate(e for e in approved if e["template"] == "T2" and _DOLLAR.search(e["question"])):
        found = _T2.match(a["sql"])
        if not found:
            continue
        word = SPELLINGS[index % len(SPELLINGS)]
        jobs.append({**a, "job_id": f"li1-{len(jobs)}", "kind": "LI1", "from": a["spec"],
                     "question": _DOLLAR.sub(word, a["question"], count=1),
                     "sql": f"SELECT SUM(total_lbp) AS total_spent_lbp FROM receipts WHERE {found.group('where')}"})
    totals = [e for e in approved if e["template"] == "T1" and (m := _T1.match(e["sql"])) and "vendor" not in m.group("where")]
    rng.shuffle(totals)
    for kind, count in WANT.items():
        for index, a in enumerate(totals[:count] if kind == "LI2" else totals[count: count * 2]):
            where = _T1.match(a["sql"]).group("where")
            if kind == "LI2":
                question = _with_word(a["question"], SPELLINGS[index % len(SPELLINGS)])
                sql = f"SELECT SUM(total_lbp) AS total_spent_lbp FROM receipts WHERE {where}"
            else:
                question = _with_word(a["question"].rstrip(" ?.!") + ", bas li dafa3to", "bel lira")
                sql = f"SELECT SUM(total) AS total_spent FROM receipts WHERE currency = 'LBP' AND {where}"
            jobs.append({**a, "job_id": f"{kind.lower()}-{len(jobs)}", "kind": kind, "from": a["spec"],
                         "question": question, "sql": sql})
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
                    job["names"], job["today"] = asdict(names), user.today.isoformat()
                    result = services.assistant.run_query(user_id, rules.prepare(guard.check(job["sql"]), names, user.today))
                    job["rows"] = _rows(result)
                    job["value"] = str(result.rows[0][0]) if result.rows else None
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs), encoding="utf-8")
    return jobs


def replay(jobs_file: Path = JOBS_FILE, out_dir: Path = DATA_DIR) -> dict:
    jobs = [json.loads(line) for line in jobs_file.read_text(encoding="utf-8").splitlines()]
    keep = ("job_id", "user", "question", "sql")
    if [{k: j[k] for k in keep} for j in jobs] != [{k: j[k] for k in keep} for j in plan()]:
        raise ValueError("the saved jobs are not the plan: prepare again")
    out, empty = {"train": [], "validation": []}, []
    for job in jobs:
        if not job["rows"] or job["value"] in (None, "None"):  # no receipts (or none in lira) in that period
            empty.append(job["job_id"])
            continue
        prompt = build_prompt(job["question"], UserNames(**job["names"]), date.fromisoformat(job["today"]), (),
                              gender=gender_of(job["user"]))  # fmt: skip
        labels = {"template": job["kind"], "kind": "sql", "language": job["language"], "user": job["user"],
                  "split": job["split"], "spec": job["job_id"], "part": "lira", "from_spec": job["from"],
                  "result_rows": job["rows"]}  # fmt: skip
        out[job["split"]].append({"messages": [{"role": "user", "content": prompt},
                                               {"role": "assistant", "content": job["sql"]}], "labels": labels})
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in out.items():
        (out_dir / f"lira_{split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                     encoding="utf-8")  # fmt: skip
    return {split: dict(Counter(r["labels"]["template"] for r in rows)) for split, rows in out.items()} | {
        "empty, left out": empty}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for flag in ("--plan", "--prepare", "--replay"):
        mode.add_argument(flag, action="store_true")
    args = parser.parse_args(argv)
    if args.plan:
        for j in plan():
            print(j["job_id"], j["user"], "|", j["question"], "|", j["sql"][:90])
    elif args.prepare:
        saved = prepare()
        print(len(saved), "jobs; empty:", [j["job_id"] for j in saved if not j["rows"] or j["value"] in (None, "None")])
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
