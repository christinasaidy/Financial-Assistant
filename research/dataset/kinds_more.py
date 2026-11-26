"""Batch 5 part 4, more: Christina's own added lines, and the end of the month (decided with her on 2026-11-22).

    python -m research.dataset.kinds_more --prepare   # plan, seed each user (with any extra receipts), run every target
    python -m research.dataset.kinds_more --replay    # the reviewed lines -> data/batch5/kinds_more_{split}.jsonl

- Her lines (raw/batch5/part4_review.md, added by her): each on a user it fits. When no user has the receipts a line
  needs (clothes shops last week, Bershka, Nike, Mike Sports), the user is given a few, for these questions only
  (seeded and removed like every user; as part 3's rent users). Her "la2ile ekher fatoura eende yeha mn Coop" is a
  new kind: the latest receipt from a shop.
- The end of the month = its last 10 days, the 21st to the end (her rulings): "bi ekher heda el shaher" this month,
  "b ekher shaher teshreen" a named month, "bi ekher hedek el shaher" in a chat the month named just before; "bi
  ekher el shaher" alone -> the question back "azdak ekher 10 iyem mn hal shaher?", and "eh" -> this month's end.
"""

import argparse
import json
import random
import re
import tempfile
from collections import Counter
from dataclasses import asdict, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.domain.assistant.prompt import Exchange, UserNames, build_prompt

from research.dataset import batch5, build, periods, smalltalk
from research.dataset import templates as t
from research.dataset.batch5 import _target
from research.dataset.checks import near_duplicate
from research.dataset.genders import FORMS
from research.dataset.kinds import users
from research.dataset.periods import Period
from research.dataset.rerender import read_prompt
from research.dataset.users import PlannedLine, PlannedReceipt, gender_of, remove_user, seed_user
from research.dataset.words import WordsError, _rows

RAW_DIR = build.RAW_DIR / "batch5" / "kinds"
JOBS_FILE = RAW_DIR / "more_jobs.jsonl"
REVIEWED = RAW_DIR / "more_reviewed.json"
DATA_DIR = build.DATA_DIR / "batch5"
END_OF_MONTH_QUESTION = next(f for f in FORMS if f.man == "CLARIFY: azdak ekher 10 iyem mn hal shaher?")


def _line(item: str, price: str) -> PlannedLine:
    return PlannedLine(item, None, None, None, Decimal(1), Decimal(price), Decimal(price), None)


def _receipt(day: date, shop: str, *lines: PlannedLine) -> PlannedReceipt:
    return PlannedReceipt(day, shop, "USD", sum((line.line_total for line in lines), Decimal(0)), "Shopping", lines)


def _extra(number: int, today: date) -> tuple[PlannedReceipt, ...]:
    """The receipts a user is given for her lines (none for the others)."""
    last_week = periods.last_week(today).start
    last_month = periods.last_month(today).start
    return {
        46: (_receipt(last_week + timedelta(days=1), "Pull and Bear", _line("t-shirt", "19.90"), _line("dress", "45.90")),
             _receipt(last_week + timedelta(days=4), "Zara", _line("dress", "59.90"))),
        44: (_receipt(last_week + timedelta(days=2), "Bershka", _line("t-shirt", "15.90"), _line("jacket", "49.90")),),
        45: (_receipt(last_month + timedelta(days=9), "Nike", _line("t-shirt", "35.00"), _line("sneakers", "110.00")),),
        47: (_receipt(today - timedelta(days=40), "Mike Sports", _line("sneakers", "89.00"), _line("socks", "9.50")),
             _receipt(today - timedelta(days=100), "Mike Sports", _line("t-shirt", "24.00"))),
    }.get(number, ())  # fmt: skip


def user_with_extra(number: int, data):
    extra = _extra(number, data.today)
    if not extra:
        return data.user
    user = data.user
    return replace(user, shops=tuple(dict.fromkeys((*user.shops, *(r.shop for r in extra)))),
                   items=tuple(dict.fromkeys((*user.items, *(line.item for r in extra for line in r.lines)))),
                   receipts=(*user.receipts, *extra))  # fmt: skip


def end_of_month(today: date, month: int | None = None) -> Period:
    """The 21st to the end of this month, or of a named month (the latest one before today)."""
    if month is None:
        start = today.replace(day=21)
        sql = ("receipt_date >= date_trunc('month', CURRENT_DATE) + INTERVAL '20 days' "
               "AND receipt_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'")
        return Period("end_of_this_month", sql, start, periods._next_month(start.replace(day=1)),
                      "at the end of this month (the 21st to its last day)", ("bi ekher heda el shaher",
                                                                              "bi ekher hal shaher"))  # fmt: skip
    named = periods.named_month(today, month)
    start = named.start + timedelta(days=20)
    return Period(f"end_of_month_{month}", f"receipt_date >= '{start}' AND receipt_date < '{named.end}'", start,
                  named.end, f"at the end of {named.description} (the 21st to its last day)", named.words)


def _money(p: Period, what: str = "") -> str:
    view, amount = ("purchases", "line_total") if what.startswith("item_name") else ("receipts", "total")
    return t.money(view, amount, what, p.sql)


def _visits(p: Period, shop: str) -> str:
    return f"SELECT COUNT(DISTINCT receipt_id) AS visits FROM receipts{t._where(f'vendor = {t.quoted(shop)}', p.sql)}"


def _shop_list(p: Period, shops: list[str]) -> str:
    where = t._where("vendor IN (" + ", ".join(t.quoted(s) for s in shops) + ")", p.sql)
    return (f"SELECT vendor, currency, SUM(total) AS total_spent, SUM(total_usd) AS total_spent_usd FROM receipts{where} "
            "GROUP BY vendor, currency ORDER BY total_spent_usd DESC")


def plan() -> list[dict]:
    everyone = {n: (s, d) for n, s, d in users()}
    today = {n: d.today for n, (s, d) in everyone.items()}
    lw, lm, tm = (lambda n: periods.last_week(today[n])), (lambda n: periods.last_month(today[n])), (
        lambda n: periods.this_month(today[n]))  # fmt: skip
    dining = "category = 'Dining'"
    restaurant_visits = (f"SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM category_spending"
                         f"{t._where(dining, tm(48).sql)} GROUP BY vendor ORDER BY visits DESC")
    jobs = [  # her lines: (id, user, template, target)
        ("h-clothes", 46, "N1", _shop_list(lw(46), ["Pull and Bear", "Zara"])),
        ("h-restaurants", 48, "N2", restaurant_visits),
        ("h-coop", 37, "N11", "SELECT receipt_date, vendor, currency, total, total_usd FROM receipts WHERE vendor = "
                              "'Coop' ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1"),
        ("h-bershka", 44, "N3", f"SELECT receipt_date, item_name, currency, line_total FROM purchases WHERE vendor = "
                                f"'Bershka' AND {lw(44).sql} ORDER BY receipt_date"),
        ("h-nike", 45, "N3", f"SELECT receipt_date, item_name, currency, line_total FROM purchases WHERE vendor = 'Nike' "
                             f"AND {lm(45).sql} ORDER BY receipt_date"),
        ("h-mike", 47, "N3", "SELECT receipt_date, item_name, currency, line_total FROM purchases WHERE vendor = "
                             "'Mike Sports' ORDER BY receipt_date"),
        ("h-top2", 37, "N4", f"SELECT item_name, SUM(line_total_usd) AS total_spent_usd FROM purchases WHERE "
                             f"{lw(37).sql} GROUP BY item_name ORDER BY total_spent_usd DESC LIMIT 2"),
        ("h-clothes-price", 48, "N5", "SELECT item_name, MAX(line_total_usd / quantity) AS price_usd FROM purchases "
                                      "WHERE " + t.items_in(sorted(n for n in everyone[48][1].items if everyone[48][1]
                                                                   .catalogue.item(n).group == "clothes")) +
                                      " GROUP BY item_name ORDER BY price_usd DESC LIMIT 5"),
    ]  # fmt: skip
    out = [{"job_id": i, "user": n, "template": tpl, "target": sql, "kind": "her line"} for i, n, tpl, sql in jobs]
    # The end of this month: users whose today is the 21st or later and who bought something since.
    late = [(33, "total"), (37, "item"), (45, "visits"), (48, "total"), (41, "total")]
    for n, what in late:
        data, p = everyone[n][1], end_of_month(today[n])
        bought = [r for r in data.user.receipts if p.start <= r.day <= today[n]]
        if what == "item":
            item = sorted({line.item for r in bought for line in r.lines})[0]
            target, label = _money(p, t.item_is(item)), item
        elif what == "visits":
            shop = Counter(r.shop for r in bought).most_common(1)[0][0]
            target, label = _visits(p, shop), shop
        else:
            target, label = _money(p), None
        out.append({"job_id": f"e-this-{n}", "user": n, "template": "N12", "target": target, "kind": "end of month",
                    "about": label})
    # The end of a named month: the month before last, on users who bought then.
    for n in (39, 43, 49, 34):
        month = (today[n].replace(day=1) - timedelta(days=40)).month
        p = end_of_month(today[n], month)
        if not any(p.start <= r.day < p.end for r in everyone[n][1].user.receipts):
            continue
        out.append({"job_id": f"e-named-{n}", "user": n, "template": "N12", "target": _money(p), "kind": "end of month",
                    "about": p.description})
    # "bi ekher hedek el shaher" in a chat, after a question about a named month (both turns written for her review:
    # no reviewed batch 3-4 question about a named month is rebuilt exactly from its pieces).
    for n in (39, 43, 49, 34):
        month = (today[n].replace(day=1) - timedelta(days=40)).month
        whole, end = periods.named_month(today[n], month), end_of_month(today[n], month)
        if not any(end.start <= r.day < end.end for r in everyone[n][1].user.receipts):
            continue
        out.append({"job_id": f"e-that-{n}", "user": n, "template": "N12", "kind": "end of that month",
                    "first_target": _money(whole), "target": _money(end), "about": whole.description})
    # "el jem3a li ra7et" is usually last week, sometimes last Friday (her review 2026-11-22): one example of the day,
    # "nhar el jem3a li ra7" = the most recent Friday before today, on the first train user who bought something then.
    for n, split, data in users():
        friday = periods.weekday(today[n] - timedelta(days=1), 4)
        if split == "train" and data.receipts_in(friday):
            out.append({"job_id": f"e-friday-{n}", "user": n, "template": "N12", "kind": "last friday",
                        "target": _money(friday)})
            break
    # "bi ekher el shaher" alone: the question back; on two users the answer "eh" follows.
    for n in (33, 45, 37):
        out.append({"job_id": f"e-ask-{n}", "user": n, "template": "C4", "kind": "ask", "target": None})
    for n in (33, 45):
        out.append({"job_id": f"e-yes-{n}", "user": n, "template": "N12", "kind": "answered",
                    "target": _money(end_of_month(today[n]))})
    for job in out:
        job["split"] = everyone[job["user"]][0]
        job["today"] = today[job["user"]].isoformat()
    return out


def prepare(jobs_file: Path = JOBS_FILE) -> list[dict]:
    jobs = plan()
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    data = {n: d for n, _, d in users()}
    for number in sorted({j["user"] for j in jobs}):
        user = user_with_extra(number, data[number])
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                for job in (j for j in jobs if j["user"] == number):
                    job["names"] = asdict(names)
                    job["rows"] = _rows(services.assistant.run_query(user_id, rules.prepare(
                        guard.check(job["target"]), names, user.today))) if job["target"] else None  # fmt: skip
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs), encoding="utf-8")
    return jobs


# --- replay ---


def _example(question: str, history, job: dict, reply: str, language: str) -> dict:
    prompt = build_prompt(question, UserNames(**job["names"]), date.fromisoformat(job["today"]), tuple(history),
                          gender=gender_of(job["user"]))  # fmt: skip
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}],
            "labels": {"template": job["template"], "kind": "clarify" if reply.startswith("CLARIFY") else "sql",
                       "language": language, "user": job["user"], "split": job["split"], "spec": job["job_id"],
                       "result_rows": job.get("rows"), "history": len(history), "part": "kinds",
                       "source": job["kind"]}}  # fmt: skip


def examples(jobs: list[dict], reviewed: dict) -> list[dict]:
    if set(reviewed) != {j["job_id"] for j in jobs}:
        raise WordsError(f"reviewed {sorted(set(reviewed) ^ {j['job_id'] for j in jobs})} differ from the plan")
    by_id = {j["job_id"]: j for j in jobs}
    out = []
    for job_id, line in reviewed.items():
        job = by_id[job_id]
        if job["kind"] == "answered":  # "bi ekher el shaher" -> the question back -> "eh"
            ask = next(j for j in jobs if j["job_id"] == job_id.replace("yes", "ask"))
            history = [Exchange(reviewed[ask["job_id"]]["question"], END_OF_MONTH_QUESTION.man)]
        elif job.get("first_target"):
            smalltalk._check_line(job_id, line["language"], line["first"], job["first_target"])
            history = [Exchange(line["first"], job["first_target"])]
        else:
            history = []
        reply = END_OF_MONTH_QUESTION.man if job["kind"] == "ask" else job["target"]
        smalltalk._check_line(job_id, line["language"], line["question"], reply)
        out.append(_example(line["question"], history, job, reply, line["language"]))
    return out


def replay(reviewed_file: Path = REVIEWED, jobs_file: Path = JOBS_FILE, out_dir: Path = DATA_DIR,
           held_out: tuple[str, ...] | None = None) -> dict:  # fmt: skip
    jobs = [json.loads(line) for line in jobs_file.read_text(encoding="utf-8").splitlines()]
    keep = ("job_id", "user", "template", "target")
    if [{k: j.get(k) for k in keep} for j in jobs] != [{k: j.get(k) for k in keep} for j in plan()]:
        raise WordsError("the saved jobs are not the plan: prepare again")
    found = examples(jobs, json.loads(reviewed_file.read_text(encoding="utf-8")))
    held_out = build.test_questions(None) if held_out is None else held_out
    out, near = {"train": [], "validation": []}, 0
    for example in found:
        if near_duplicate(read_prompt(example["messages"][0]["content"]).question, held_out):
            near += 1
            continue
        out[example["labels"]["split"]].append(example)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in out.items():
        (out_dir / f"kinds_more_{split}.jsonl").write_text(
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
        print(len(saved), "jobs:", dict(Counter(j["kind"] for j in saved)),
              "| empty:", [j["job_id"] for j in saved if j["rows"] == 0])
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
