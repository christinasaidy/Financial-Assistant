"""Batch 5: "the pharmacy" when the user has two (her rulings and lines, 2026-11-22; PROGRESS.md).

    python -m research.dataset.pharmacies --prepare   # seed each user, run every target as the app would -> jobs.jsonl
    python -m research.dataset.pharmacies --replay    # -> data/batch5/pharmacies_{split}.jsonl

Her rulings: "-et" before a name is not plural ("saydaliyet Mazen" = Mazen's pharmacy, one shop); "el saydaliyet" =
the pharmacies, all of them; "el saydaliye" (one, no name) when the user has more than one: ask which, naming them;
with one, that one. English the same ("the pharmacy" asks; "pharmacies", "a pharmacy" add them all). "Both" as the
answer to the question back: tnayneton, tnainetin, el tnen, l tnayn.

Her approved lines, on the users who have Pharmacie Mazloum and Pharmacie Nassar (and two with only one): questions
back, chats where the user answers one or both, the plural adding both up, and one pharmacy needing no question.
The question back uses the printed names ("azdak Pharmacie Mazloum aw Pharmacie Nassar?"), so the made-up shop names
of shop_names.py swap them like any other; its woman and neutral forms are genders.PHARMACIES. Every query runs
through the app on the seeded user (removed after). The 6 stored questions this changes are fixed in fixes.py.
"""

import argparse
import json
import tempfile
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.domain.assistant.prompt import Exchange, UserNames, build_prompt

from research.dataset import build
from research.dataset import templates as t
from research.dataset.users import gender_of, remove_user, seed_user
from research.dataset.words import _rows, users

RAW_DIR = build.RAW_DIR / "batch5" / "pharmacies"
JOBS_FILE = RAW_DIR / "jobs.jsonl"
DATA_DIR = build.DATA_DIR / "batch5"
BOTH = ("Pharmacie Mazloum", "Pharmacie Nassar")

THIS_MONTH = ("receipt_date >= date_trunc('month', CURRENT_DATE) AND receipt_date < date_trunc('month', CURRENT_DATE) "
              "+ INTERVAL '1 month'")  # fmt: skip
THIS_YEAR = "receipt_date >= date_trunc('year', CURRENT_DATE)"
LAST_3_MONTHS = "receipt_date > CURRENT_DATE - INTERVAL '3 months' AND receipt_date <= CURRENT_DATE"


def vendors(*names: str) -> str:
    return f"vendor = {t.quoted(names[0])}" if len(names) == 1 else f"vendor IN ({', '.join(map(t.quoted, names))})"


def spent(names, period) -> str:
    return (f"SELECT currency, SUM(total) AS total_spent, SUM(total_usd) AS total_spent_usd FROM receipts WHERE "
            f"{vendors(*names)} AND {period} GROUP BY currency")  # fmt: skip


def visits(names, period) -> str:
    return f"SELECT COUNT(DISTINCT receipt_id) AS visits FROM receipts WHERE {vendors(*names)} AND {period}"


def last_time(names) -> str:
    return f"SELECT MAX(receipt_date) AS last_time FROM receipts WHERE {vendors(*names)}"


def last_items(names) -> str:
    return (f"SELECT receipt_date, item_name, currency, line_total FROM purchases WHERE receipt_id = (SELECT receipt_id "
            f"FROM receipts WHERE {vendors(*names)} ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1)")  # fmt: skip


def ask(names=BOTH, english=False) -> str:
    """The question back, in the man's form (genders.PHARMACIES gives the others)."""
    return f"CLARIFY: {names[0]} or {names[1]}?" if english else f"CLARIFY: azdak {names[0]} aw {names[1]}?"


ONE = ("Pharmacie Mazloum",)
# (job id, user, language, earlier question or None, question, reply, template)
LINES = (
    # questions back (one, no name, two pharmacies)
    ("ph-t-0", 37, "arabizi", None, "aday sarafet bel saydaliye hal shaher?", ask(), "PH1"),
    ("ph-t-1", 46, "arabizi", None, "emta ekher marra rehet 3al saydaliye?", ask(), "PH1"),
    ("ph-t-2", 43, "arabizi", None, "kam marra ro7t 3al pharmacie hal sene?", ask(), "PH1"),
    ("ph-t-3", 45, "arabizi", None, "shu shtrit mn el saydaliye ekher marra?", ask(), "PH1"),
    ("ph-t-4", 38, "english", None, "How much did I spend at the pharmacy last month?", ask(english=True), "PH1"),
    # chats: the question back, then one or both
    ("ph-t-5", 43, "arabizi", "aday sarafet bel saydaliye hal shaher?", "Mazloum", spent(ONE, THIS_MONTH), "PH2"),
    ("ph-t-6", 45, "arabizi", "adesh sarafet bel saydaliye hal shaher?", "tnayneton", spent(BOTH, THIS_MONTH), "PH2"),
    ("ph-t-7", 43, "arabizi", "kam marra rehet 3al saydaliye hal sene?", "el tnen", visits(BOTH, THIS_YEAR), "PH2"),
    ("ph-t-8", 45, "arabizi", "emta ekher marra rehet 3al pharmacie?", "Nassar", last_time(("Pharmacie Nassar",)), "PH2"),
    ("ph-t-9", 37, "arabizi", "aday dafa3et bel saydaliye hal sene?", "l tnayn", spent(BOTH, THIS_YEAR), "PH2"),  # her line said
    # "ekher shaher": no train user with both pharmacies went to one last month, so the period is this year
    ("ph-t-10", 43, "arabizi", "adesh dafa3et bel saydaliye hal shaher?", "tnainetin", spent(BOTH, THIS_MONTH), "PH2"),
    # the plural adds them all
    ("ph-t-11", 45, "arabizi", None, "aday sarafet bel saydaliyet hal shaher?", spent(BOTH, THIS_MONTH), "PH3"),
    ("ph-t-12", 46, "arabizi", None, "kam marra rehet 3al saydaliyet ekher 3 shhour?", visits(BOTH, LAST_3_MONTHS), "PH3"),
    ("ph-t-13", 43, "english", None, "How much did I spend at pharmacies this year?", spent(BOTH, THIS_YEAR), "PH3"),
    # one pharmacy: no question
    ("ph-t-14", 48, "arabizi", None, "aday sarafet bel saydaliye hal shaher?", spent(ONE, THIS_MONTH), "PH4"),
    ("ph-t-15", 44, "arabizi", None, "emta ekher marra rehet 3al pharmacie?", last_time(ONE), "PH4"),
    # validation
    ("ph-v-16", 41, "arabizi", None, "adesh dafa3et bel saydaliye hal shaher?", ask(), "PH1"),
    ("ph-v-17", 50, "arabizi", "aday sarafet bel saydaliye hal shaher?", "Mazloum", spent(ONE, THIS_MONTH), "PH2"),
)  # fmt: skip


def plan() -> list[dict]:
    splits = {n: s for n, s, _ in users()}
    jobs = []
    for job_id, user, language, earlier, question, reply, template in LINES:
        expected = "validation" if job_id.startswith("ph-v") else "train"
        if splits[user] != expected:
            raise ValueError(f"{job_id}: user {user} is not a {expected} user")
        jobs.append({"job_id": job_id, "user": user, "split": expected, "language": language, "earlier": earlier,
                     "question": question, "reply": reply, "template": template})  # fmt: skip
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
                    shops = [v for v in names.vendors if v.startswith("Pharmacie")]
                    wanted = list(ONE) if job["template"] == "PH4" else list(BOTH)
                    if sorted(shops) != wanted:
                        raise ValueError(f"{job['job_id']}: user {number} has {shops}, not {wanted}")
                    job["rows"] = None if job["reply"].startswith("CLARIFY") else _rows(services.assistant.run_query(
                        user_id, rules.prepare(guard.check(job["reply"]), names, user.today)))  # fmt: skip
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs), encoding="utf-8")
    return jobs


def replay(jobs_file: Path = JOBS_FILE, out_dir: Path = DATA_DIR) -> dict:
    jobs = [json.loads(line) for line in jobs_file.read_text(encoding="utf-8").splitlines()]
    keep = ("job_id", "user", "question", "reply", "earlier")
    if [{k: j[k] for k in keep} for j in jobs] != [{k: j[k] for k in keep} for j in plan()]:
        raise ValueError("the saved jobs are not the plan: prepare again")
    out = {"train": [], "validation": []}
    for job in jobs:
        names, today = UserNames(**job["names"]), date.fromisoformat(job["today"])
        history = (Exchange(job["earlier"], ask()),) if job["earlier"] else ()
        prompt = build_prompt(job["question"], names, today, history, gender=gender_of(job["user"]))
        kind = "clarify" if job["reply"].startswith("CLARIFY") else "sql"
        labels = {"template": job["template"], "kind": kind, "language": job["language"], "user": job["user"],
                  "split": job["split"], "spec": job["job_id"], "part": "pharmacies", "history": len(history)}  # fmt: skip
        if job["rows"] is not None:
            labels["result_rows"] = job["rows"]
        out[job["split"]].append({"messages": [{"role": "user", "content": prompt},
                                               {"role": "assistant", "content": job["reply"]}], "labels": labels})
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in out.items():
        (out_dir / f"pharmacies_{split}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return {split: len(rows) for split, rows in out.items()} | {
        "empty answers": [j["job_id"] for j in jobs if j["rows"] == 0]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare:
        saved = prepare()
        print(len(saved), "jobs; rows:", {j["job_id"]: j["rows"] for j in saved})
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
