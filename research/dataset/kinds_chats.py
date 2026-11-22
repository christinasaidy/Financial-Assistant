"""Batch 5 part 4 in chats, and the questions back about prices in general (decided with Christina on 2026-11-22).

    python -m research.dataset.kinds_chats --prepare   # plan the chats, seed each user, run every target
    python -m research.dataset.kinds_chats --replay    # her reviewed lines -> data/batch5/kinds_chats_{split}.jsonl

- list: a stored "the top one" question (aktar shi, LIMIT 1) and its answer, then "w 3edele hene kelon" -> the same
  query without LIMIT 1 (every shop, most first);
- last year: a stored "how much on <item>" question and its answer, then "w el sene el madye?" -> the same item,
  last calendar year (her ruling: el sene el madye = last calendar year);
- prices: "wen arkhas mahal la jib khodra bi beirut?" -> the question back of genders.PRICES ("ma fiye 2elak 3an kel
  beirut, bas fiye shuf wen jebta arkhas mn fwatirak ..."), then the user names a vegetable ("khyar") -> where it was
  cheapest among the shops they bought it at (batch 3's cheapest-anywhere query), and sometimes another one
  ("w el banadoura?"). Each answered turn is an example.
- general: the same price questions alone (and "aya supermarket arkhas bi lebnen?" -> the shops form), on stored
  users.

The questions back are stored in the man's form; the mix gives each user their form (genders.for_gender).
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

from app.domain.assistant.prompt import Exchange, UserNames, build_prompt

from research.dataset import batch3, batch5, build, deciding, periods, smalltalk
from research.dataset import templates as t
from research.dataset.batch5 import _target
from research.dataset.checks import near_duplicate
from research.dataset.genders import PRICES
from research.dataset.kinds import users
from research.dataset.rerender import read_prompt
from research.dataset.users import gender_of, remove_user, seed_user
from research.dataset.words import WordsError, _rows

RAW_DIR = build.RAW_DIR / "batch5" / "kinds"
JOBS_FILE = RAW_DIR / "chat_jobs.jsonl"
REVIEWED = RAW_DIR / "chats_reviewed.json"
DATA_DIR = build.DATA_DIR / "batch5"
SEED = "fyp-dataset/batch5-kinds-chats"

# The price chats: (user, split, the vegetables they name in turn). Each was bought at 2 or more shops.
PRICE_CHATS = ((34, "train", ("cucumber", "tomatoes")), (49, "train", ("cucumber",)), (32, "train", ("potatoes",
               "tomatoes")), (44, "train", ("lettuce", "potatoes")), (50, "validation", ("cucumber",)))  # fmt: skip
LIST_CHATS, LAST_YEAR_CHATS, THERE_CHATS = 6, 4, 6


def _period_of(sql: str) -> str:
    """The date conditions of a stored query (the period a follow-up carries over)."""
    where = re.search(r" WHERE (.*?)(?: GROUP BY .*)?$", sql)
    parts = re.split(r" AND (?![^()]*\))", where.group(1)) if where else []
    return " AND ".join(part for part in parts if "receipt_date" in part)


def there_target(first_sql: str, measure: str) -> str:
    """"honik" after a top-one shop answer: the shop is the earlier query's answer, so the earlier query (unchanged)
    picks it; the period carries over (her decision 2026-11-22: "w kam marra rehet la honik?")."""
    shop = f"vendor = (SELECT vendor FROM ({first_sql}) AS earlier)"
    period = _period_of(first_sql)
    if measure == "visits":
        return f"SELECT COUNT(DISTINCT receipt_id) AS visits FROM receipts{t._where(shop, period)}"
    if measure == "money":
        return t.money("receipts", "total", shop, period)
    return f"SELECT receipt_date, item_name, currency, line_total FROM purchases{t._where(shop, period)} ORDER BY receipt_date"


def _cheapest(data, item: str) -> str:
    units = batch3._units(data, item)
    unit = next(u for u, shops in sorted(units.items(), key=lambda kv: str(kv[0])) if len(shops) >= 2)
    return batch3._comparison(item, (), unit, order=True)


def plan() -> list[dict]:
    everyone = {n: (s, d) for n, s, d in users()}
    stored = batch5.load_stored()
    rng = random.Random(SEED)
    jobs = []
    tops = [s for n in batch5.TRAIN for s in stored[n] if s.kind == "sql" and s.target.startswith("SELECT vendor")
            and s.target.endswith(" LIMIT 1") and any(lang != "english" for lang, _ in s.versions)]  # fmt: skip
    rng.shuffle(tops)
    picked, seen_users = [], set()
    for s in tops:
        if s.user not in seen_users and len(picked) < LIST_CHATS:
            picked.append(s)
            seen_users.add(s.user)
    for i, s in enumerate(picked):
        question = next(q for lang, q in s.versions if lang != "english")
        jobs.append({"job_id": f"kc-list-{i}", "user": s.user, "split": "train", "kind": "list", "first_spec": s.spec,
                     "turns": [[question, s.target]], "target": s.target.removesuffix(" LIMIT 1")})
    used = {j["first_spec"] for j in jobs}
    # every other top-one question, longer periods first (after "yesterday" a visit count is almost always 1), one per
    # user; after "the place I went to most" the follow-up asks money or purchases, not visits again
    there, seen = [], set()
    for s in sorted((s for s in tops if s.spec not in used), key=lambda s: ("CURRENT_DATE - 1" in s.target,
                                                                            "COUNT(DISTINCT receipt_id)" in s.target)):
        if s.user not in seen:
            seen.add(s.user)
            there.append(s)
    for i, s in enumerate(there[:THERE_CHATS]):
        question = next(q for lang, q in s.versions if lang != "english")
        visits_first = "COUNT(DISTINCT receipt_id)" in s.target
        measure = ("money", "bought")[i % 2] if visits_first else "visits"  # money first -> "kam marra rehet la honik?"
        jobs.append({"job_id": f"kc-there-{i}", "user": s.user, "split": "train", "kind": "there", "measure": measure,
                     "first_spec": s.spec, "turns": [[question, s.target]], "target": there_target(s.target, measure)})
    items = [s for n in batch5.TRAIN for s in stored[n] if s.template == "T9" and s.view and s.what.startswith(
        "item_name") and any(lang != "english" for lang, _ in s.versions)]  # fmt: skip
    rng.shuffle(items)
    seen_users = set()
    for s in items:
        if len([j for j in jobs if j["kind"] == "last year"]) == LAST_YEAR_CHATS:
            break
        data = everyone[s.user][1]
        last = periods.last_year(data.today)
        if s.user in seen_users or not data.bought(last, batch5._item_name(s.what)):
            continue
        seen_users.add(s.user)
        question = next(q for lang, q in s.versions if lang != "english")
        jobs.append({"job_id": f"kc-year-{len(seen_users) - 1}", "user": s.user, "split": "train", "kind": "last year",
                     "first_spec": s.spec, "turns": [[question, s.target]],
                     "target": _target(s.view, "money", s.what, last.sql)})  # fmt: skip
    for i, (number, split, vegetables) in enumerate(PRICE_CHATS):
        data = everyone[number][1]
        jobs.append({"job_id": f"kc-price-{i}", "user": number, "split": split, "kind": "prices", "first_spec": None,
                     "vegetables": list(vegetables), "targets": [_cheapest(data, v) for v in vegetables]})
    for job in jobs:
        job["today"] = everyone[job["user"]][1].today.isoformat()
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
                run = lambda sql: _rows(services.assistant.run_query(user_id, rules.prepare(  # noqa: E731
                    guard.check(sql), names, user.today)))
                for job in (j for j in jobs if j["user"] == number):
                    job["names"] = asdict(names)
                    job["rows"] = [run(sql) for sql in job.get("targets", [job.get("target")])]
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs), encoding="utf-8")
    return jobs


# --- replay ---


def price_reply(line: dict) -> str:
    """The question back, in the man's form (the mix gives each user theirs); "aya khodra?" alone when short."""
    if line.get("short"):
        return f"CLARIFY: aya {line['thing']}?"
    return PRICES[line["form"]].man.format(x=line["place"], y=line["thing"])


def _example(question, history, job, reply, labels) -> dict:
    prompt = build_prompt(question, UserNames(**job["names"]), date.fromisoformat(job["today"]), tuple(history),
                          gender=gender_of(job["user"]))  # fmt: skip
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}],
            "labels": {"kind": "sql" if reply.startswith("SELECT") else "clarify", "user": job["user"],
                       "split": job["split"], "spec": job["job_id"], "history": len(history), "part": "kinds",
                       **labels}}  # fmt: skip


def chat_examples(jobs: list[dict], reviewed: dict) -> list[dict]:
    lines = reviewed["chats"]
    if set(lines) != {j["job_id"] for j in jobs}:
        raise WordsError(f"reviewed chats {sorted(lines)} are not the planned ones")
    out = []
    for job in jobs:
        line = lines[job["job_id"]]
        if job["kind"] in ("list", "last year", "there"):
            smalltalk._check_line(job["job_id"], line["language"], line["question"], job["target"])
            history = [Exchange(q, r) for q, r in job["turns"]]
            out.append(_example(line["question"], history, job, job["target"], {
                "template": {"list": "K4L", "last year": "K4Y", "there": "K4T"}[job["kind"]], "language": line["language"],
                "result_rows": job["rows"][0], "first_spec": job["first_spec"]}))  # fmt: skip
            continue
        first = line["first"]
        history = [Exchange(first["question"], price_reply(first))]
        if len(line["answers"]) != len(job["targets"]):
            raise WordsError(f"{job['job_id']}: {len(line['answers'])} answers for {len(job['targets'])} vegetables")
        for answer, target, rows in zip(line["answers"], job["targets"], job["rows"], strict=True):
            smalltalk._check_line(job["job_id"], first["language"], answer, target)
            out.append(_example(answer, history, job, target, {"template": "K4P", "language": first["language"],
                                                               "result_rows": rows}))  # fmt: skip
            history.append(Exchange(answer, target))
    return out


def general_examples(reviewed: dict, pools) -> list[dict]:
    taken, out = Counter(), []
    for line in reviewed["general"]:
        row = deciding._on_user(pools, line, taken)
        reply = price_reply(line)
        smalltalk._check_line(f"kg-{line['n']}", line["language"], line["question"], reply)
        parts = read_prompt(row["messages"][0]["content"])
        labels = {"template": "C9", "kind": "clarify", "language": line["language"], "user": row["labels"]["user"],
                  "split": row["labels"]["split"], "spec": f"kg-{line['n']}", "result_rows": None, "part": "kinds"}
        out.append(deciding._example(line["question"], parts.names, parts.today, row["labels"]["user"], reply, labels))
    return out


def replay(reviewed_file: Path = REVIEWED, jobs_file: Path = JOBS_FILE, out_dir: Path = DATA_DIR,
           data_dir: Path = build.DATA_DIR, held_out: tuple[str, ...] | None = None) -> dict:  # fmt: skip
    reviewed = json.loads(reviewed_file.read_text(encoding="utf-8"))
    jobs = [json.loads(line) for line in jobs_file.read_text(encoding="utf-8").splitlines()]
    keep = ("job_id", "user", "kind", "target", "targets")
    if [{k: j.get(k) for k in keep} for j in jobs] != [{k: j.get(k) for k in keep} for j in plan()]:
        raise WordsError("the saved chat jobs are not the plan: prepare again")
    found = chat_examples(jobs, reviewed) + general_examples(reviewed, deciding.context_rows(data_dir))
    held_out = build.test_questions(None) if held_out is None else held_out
    out, near = {"train": [], "validation": []}, 0
    for example in found:
        if near_duplicate(read_prompt(example["messages"][0]["content"]).question, held_out):
            near += 1
            continue
        out[example["labels"]["split"]].append(example)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in out.items():
        (out_dir / f"kinds_chats_{split}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return {"train": len(out["train"]), "validation": len(out["validation"]), "near test questions, dropped": near,
            "kinds": dict(Counter(e["labels"]["template"] for rows in out.values() for e in rows))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for flag in ("--prepare", "--replay"):
        mode.add_argument(flag, action="store_true")
    args = parser.parse_args(argv)
    if args.prepare:
        saved = prepare()
        print(len(saved), "chats:", dict(Counter(j["kind"] for j in saved)),
              "| empty answers:", sum(1 for j in saved for r in j["rows"] if r == 0))
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
