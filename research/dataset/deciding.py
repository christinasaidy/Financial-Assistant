"""Batch 5 part 3: deciding — refuse, ask back or answer (decided with Christina on 2026-11-20; PROGRESS.md).

    python -m research.dataset.deciding --prepare   # seed the rent users, run their SQL as the app would
    python -m research.dataset.deciding --replay    # -> data/batch5/deciding_{train,validation}.jsonl

Her reviewed lines are in raw/batch5/deciding/reviewed.json (from deciding_review.md):

- A, another person's spending, and B1, income -> UNSUPPORTED; C3, a rent budget -> UNSUPPORTED (budgets cannot be
  seen by the assistant);
- B2, "where did my salary go" -> spending by category, and E, another person mentioned but the user's own data ->
  the stored question's SQL (a new version of a stored, approved question, checked like it);
- C1, rent for a user who has a Rent category -> SQL: three batch 3-4 users get a Rent category and a monthly rent
  typed in by hand, as the app allows (manual entry), seeded and always removed, their SQL run through the app;
- C2, the same rent questions for users without rent, and D, transfers or loans never entered -> CLARIFY (table G of
  genders.py; the mix gives each user their form).

Each refusal or question back goes on a stored batch 3-4 user (their names and day), of the line's gender when it
has one. Nothing is written unless every line passes its checks; a line near a test question is dropped and counted.
"""

import argparse
import hashlib
import json
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.domain.assistant.prompt import UserNames, build_prompt

from research.dataset import batch3, batch4, build, periods, smalltalk, words
from research.dataset import templates as t
from research.dataset.checks import Version, near_duplicate, problems
from research.dataset.genders import DECIDING
from research.dataset.rerender import read_prompt
from research.dataset.users import PlannedLine, PlannedReceipt, gender_of, remove_user, seed_user

RAW_DIR = build.RAW_DIR / "batch5" / "deciding"
REVIEWED = RAW_DIR / "reviewed.json"
JOBS_FILE = RAW_DIR / "rent_jobs.jsonl"
DATA_DIR = build.DATA_DIR / "batch5"
RENT = "Rent"
LANDLORD = "Abou Fadi"
# The rent users: (batch, number, monthly rent in USD). Not used for C2, so "has rent" and "has none" stay apart.
RENT_USERS = ((batch3, 37, Decimal("450.00")), (batch4, 44, Decimal("600.00")), (batch3, 33, Decimal("350.00")))
ENGLISH = {"rent": "CLARIFY: I couldn't find rent in your receipts. Did you record it under another name?",
           "transfer": "CLARIFY: I couldn't find any transfers in your receipts. Did you record them under another name?"}
TEMPLATES = {"A": "U5", "B1": "U5", "C3": "U1", "C2": "C1", "D": "C1"}


class DecidingError(ValueError):
    """A reviewed line that does not match the plan, or fails a check."""


# --- C1: the rent users and their SQL ---


def _total(p: periods.Period) -> str:
    return t.money("category_spending", "amount", f"category = {t.quoted(RENT)}", p.sql)


LAST_PAYMENT = (f"SELECT receipt_date, vendor, currency, amount FROM category_spending WHERE category = {t.quoted(RENT)} "
                "ORDER BY receipt_date DESC LIMIT 1")
LAST_TIME = f"SELECT MAX(receipt_date) AS last_time FROM category_spending WHERE category = {t.quoted(RENT)}"
# C1's question number -> (user, template, SQL from the user's day), as planned with her review of C1.
C1_PLAN = {
    1: (37, "T3", lambda d: _total(periods.this_month(d))), 6: (37, "T3", lambda d: _total(periods.named_month(d, 10))),
    14: (37, "T3", lambda d: _total(periods.named_month(d, 9))), 12: (37, "B11", lambda d: LAST_TIME),
    9: (37, "T3", lambda d: _total(periods.this_year(d))),
    2: (44, "T3", lambda d: _total(periods.last_month(d))), 4: (44, "T11", lambda d: LAST_PAYMENT),
    7: (44, "T3", lambda d: _total(periods.last_month(d))), 10: (44, "T3", lambda d: _total(periods.last_months(d, 3))),
    15: (44, "T3", lambda d: _total(periods.last_month(d))),
    3: (33, "T3", lambda d: _total(periods.this_year(d))), 5: (33, "T3", lambda d: _total(periods.since_start_of_year(d))),
    8: (33, "T11", lambda d: LAST_PAYMENT), 11: (33, "T3", lambda d: _total(periods.this_year(d))),
    13: (33, "T3", lambda d: _total(periods.this_month(d))),
}  # fmt: skip


def rent_user(module, number: int, rent: Decimal):
    """The batch user with a Rent category and the rent typed in on the 1st of each of the last 14 months."""
    catalogue = module.load_batch3_catalogue() if module is batch3 else module.load_batch4_catalogue()
    data = (module.batch3_user if module is batch3 else module.batch4_user)(number, catalogue)
    user = data.user
    first = user.today.replace(day=1)
    days = [first]
    for _ in range(13):
        days.append((days[-1] - timedelta(days=1)).replace(day=1))
    line = PlannedLine("rent", None, None, None, Decimal(1), rent, rent, None)
    receipts = tuple(PlannedReceipt(day, LANDLORD, "USD", rent, RENT, (line,)) for day in sorted(days))
    return replace(user, private_categories=(*user.private_categories, RENT), shops=(*user.shops, LANDLORD),
                   items=(*user.items, "rent"), receipts=(*user.receipts, *receipts))  # fmt: skip


def plan_rent(reviewed: dict) -> list[dict]:
    questions = {line["n"]: line for line in reviewed["C1"]}
    if set(questions) != set(C1_PLAN):
        raise DecidingError(f"C1 has {sorted(questions)}, the plan {sorted(C1_PLAN)}")
    users = {number: rent_user(module, number, rent) for module, number, rent in RENT_USERS}
    split = {n: "validation" if n in (*batch3.VALIDATION, *batch4.VALIDATION) else "train" for n in users}
    return [{"job_id": f"rent-{n}", "user": user, "split": split[user], "template": template,
             "today": users[user].today.isoformat(), "language": questions[n]["language"],
             "question": questions[n]["question"], "target": sql(users[user].today)}
            for n, (user, template, sql) in sorted(C1_PLAN.items())]  # fmt: skip


def prepare(jobs_file: Path = JOBS_FILE, reviewed_file: Path = REVIEWED) -> list[dict]:
    jobs = plan_rent(json.loads(reviewed_file.read_text(encoding="utf-8")))
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    for module, number, rent in RENT_USERS:
        user = rent_user(module, number, rent)
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                for job in (j for j in jobs if j["user"] == number):
                    result = services.assistant.run_query(user_id, rules.prepare(guard.check(job["target"]), names,
                                                                                 user.today))  # fmt: skip
                    job["rows"] = sum(1 for row in result.rows if any(v not in (None, 0) for v in row))
                    job["names"] = asdict(names)
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs), encoding="utf-8")
    return jobs


# --- replay ---


def _pick(options: tuple, key: str):
    return options[int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % len(options)]


def context_rows(data_dir: Path = build.DATA_DIR, leave_out: tuple[int, ...] = ()) -> dict:
    """Stored batch 3-4 examples to borrow a user's names and day from, by the user's gender (None: anyone)."""
    pools = defaultdict(list)
    for batch in ("batch3", "batch4"):
        for split in ("train", "validation"):
            for row in map(json.loads, (data_dir / batch / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()):
                if row["labels"]["user"] in leave_out or row["labels"].get("history"):
                    continue
                pools[gender_of(row["labels"]["user"]).value].append(row)
                pools[None].append(row)
    return pools


def _on_user(pools, line: dict, taken: Counter) -> dict:
    pool = pools[line.get("gender")]
    row = pool[(taken[line.get("gender")] * 37) % len(pool)]  # a stride, so neighbours are different users
    taken[line.get("gender")] += 1
    return row


def _example(question: str, names, today: date, user: int, reply: str, labels: dict) -> dict:
    prompt = build_prompt(question, names, today, (), gender=gender_of(user))
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}],
            "labels": labels}


def boundary_examples(reviewed: dict, pools) -> list[dict]:
    """A, B1, C3 (UNSUPPORTED) and C2, D (CLARIFY) on stored users."""
    lines = [(g, line) for g in ("A", "B1", "C3", "D") for line in reviewed[g]]
    lines += [("C2", dict(line, gender=None, n=f"c1-{line['n']}")) for line in reviewed["C1"]]  # on users without rent
    lines += [("C2", line) for line in reviewed.get("C2", ())]  # the 10 more she reviewed
    taken, out = Counter(), []
    for group, line in lines:
        row = _on_user(pools, line, taken)
        key = f"{group}-{line['n']}|{line['question']}"
        if group in ("A", "B1", "C3"):
            reply = "UNSUPPORTED"
        else:
            topic = "rent" if group == "C2" else "transfer"
            reply = ENGLISH[topic] if line["language"] == "english" else _pick(DECIDING[topic], key).man
        smalltalk._check_line(key, line["language"], line["question"], reply)
        labels = {"template": TEMPLATES[group], "kind": "unsupported" if reply == "UNSUPPORTED" else "clarify",
                  "language": line["language"], "user": row["labels"]["user"], "split": row["labels"]["split"],
                  "spec": f"d3-{group}-{line['n']}", "result_rows": None, "part": "deciding", "deciding": group}
        parts = read_prompt(row["messages"][0]["content"])
        out.append(_example(line["question"], parts.names, parts.today, row["labels"]["user"], reply, labels))
    return out


def without_lead_in(spec):
    """The spec without batch 4's lead-in word group ("badi a3ref ..."): a new version brings its own lead-in, and
    still has to name the item, shop and period (2026-11-20)."""
    style = spec.labels.get("lead_in")
    if style not in batch4.LEAD_INS:
        return spec
    lead = tuple(batch4.LEAD_INS[style][0])
    return replace(spec, mentions=tuple(group for group in spec.mentions if tuple(group) != lead))


def version_examples(reviewed: dict, stored: dict, specs: dict) -> list[dict]:
    """B2 and E: a new version of a stored, approved question; its SQL, user and day."""
    out = []
    for group in ("B2", "E"):
        for line in reviewed[group]:
            if line["spec"] not in stored:
                raise DecidingError(f"no stored example for {line['spec']}")
            row = stored[line["spec"]]
            found = problems(Version(line["language"], line["question"]), without_lead_in(specs[line["spec"]]),
                             words._catalogue(line["spec"]))  # fmt: skip
            if found:
                raise DecidingError(f"{group}-{line['n']} ({line['spec']}): {line['question']!r}: {'; '.join(found)}")
            smalltalk._check_line(line["spec"], line["language"], line["question"], row["messages"][1]["content"])
            if line["gender"] and gender_of(row["labels"]["user"]).value != line["gender"]:
                raise DecidingError(f"{group}-{line['n']}: said by a {line['gender']}, but {line['spec']}'s user is not")
            parts = read_prompt(row["messages"][0]["content"])
            labels = {**row["labels"], "language": line["language"], "part": "deciding", "deciding": group}
            out.append(_example(line["question"], parts.names, parts.today, row["labels"]["user"],
                                row["messages"][1]["content"], labels))  # fmt: skip
    return out


def rent_examples(jobs: list[dict]) -> list[dict]:
    out = []
    for job in jobs:
        smalltalk._check_line(job["job_id"], job["language"], job["question"], job["target"])
        labels = {"template": job["template"], "kind": "sql", "language": job["language"], "user": job["user"],
                  "split": job["split"], "spec": job["job_id"], "result_rows": job["rows"], "part": "deciding",
                  "deciding": "C1", "category": RENT}  # fmt: skip
        out.append(_example(job["question"], UserNames(**job["names"]), date.fromisoformat(job["today"]), job["user"],
                            job["target"], labels))  # fmt: skip
    return out


def replay(reviewed_file: Path = REVIEWED, jobs_file: Path = JOBS_FILE, out_dir: Path = DATA_DIR,
           data_dir: Path = build.DATA_DIR, stored_raw: Path = build.RAW_DIR,
           held_out: tuple[str, ...] | None = None) -> dict:  # fmt: skip
    reviewed = json.loads(reviewed_file.read_text(encoding="utf-8"))
    jobs = [json.loads(line) for line in jobs_file.read_text(encoding="utf-8").splitlines()]
    planned = plan_rent(reviewed)
    if [(j["job_id"], j["question"], j["target"]) for j in jobs] != [(j["job_id"], j["question"], j["target"])
                                                                    for j in planned]:  # fmt: skip
        raise DecidingError("the saved rent jobs are not the plan: prepare again")
    rent_numbers = tuple(number for _, number, _ in RENT_USERS)
    examples = boundary_examples(reviewed, context_rows(data_dir, leave_out=rent_numbers))
    examples += version_examples(reviewed, words.stored(data_dir), words.stored_specs(stored_raw))
    examples += rent_examples(jobs)
    held_out = build.test_questions(None) if held_out is None else held_out
    out, near = {"train": [], "validation": []}, 0
    for example in examples:
        if near_duplicate(read_prompt(example["messages"][0]["content"]).question, held_out):
            near += 1
            continue
        out[example["labels"]["split"]].append(example)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, found in out.items():
        (out_dir / f"deciding_{split}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in found), encoding="utf-8")
    return {"train": len(out["train"]), "validation": len(out["validation"]), "near test questions, dropped": near,
            "groups": dict(Counter(e["labels"]["deciding"] for found in out.values() for e in found)),
            "kinds": dict(Counter(e["labels"]["kind"] for found in out.values() for e in found))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare:
        jobs = prepare()
        print(len(jobs), "rent jobs | empty:", [j["job_id"] for j in jobs if not j["rows"]])
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
