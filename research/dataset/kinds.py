"""Batch 5 part 4: the missing query kinds (decided with Christina on 2026-11-22; PROGRESS.md; samples she approved in
raw/batch5/part4_examples_review.md).

    python -m research.dataset.kinds --plan      # -> raw/batch5/kinds/plan.json (the questions to write)
    python -m research.dataset.kinds --prepare   # seed each user, run every target as the app would -> jobs.jsonl
    python -m research.dataset.kinds --replay    # her reviewed versions -> data/batch5/kinds_{train,validation}.jsonl

The kinds, each built on a batch 3-4 user (their reviewed catalogue) from the batches' own SQL pieces:

- N1 every shop with its total, most first (all shops, restaurants or supermarkets): "aya mata3em rehet 3layon";
  the stored "aktar shi" questions are the top one only;
- N2 the places visited, by visits, most first ("top matare7 reht aalayon"); bills and subscriptions left out;
- N3 what the user bought at a shop, by date ("shu shtrit mn Spinneys");
- N4 the items the user spent the most on, by USD, top 3 / 5;
- N5 the priciest or cheapest items by price (USD per unit), top 1 / 3 / 5, of all, of the supermarket (Groceries)
  or of a kind of product ("arkhas 5 ota3 tyeb");
- N6 the biggest receipt ("aghla fatoura");
- N7 one item, shop or category in two months (as T17, filtered on it);
- N8 the average receipt at a shop, with the number of visits ("aday bedfa3 aadatan 3and X");
- N10 this month so far ("aday sar masroufe hal shaher la hala2");
- N9 how many different shops (bills and subscriptions left out);
- C2 the same N3 / N8 questions at a shop the user never went to: the stored "no receipts from X" question back.

Prepare seeds each user, runs every target through the app's guard, answering rules and read-only role, and always
removes the user. Each job gets 3 versions (2 Arabizi or mixed, 1 English), written by agents and reviewed by her;
every version must pass the stored questions' checks (checks.problems) and have no rejected spelling.
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

from research.dataset import batch3, batch4, build, periods
from research.dataset.answers_build import REJECTED
from research.dataset import templates as t
from research.dataset.batch2_build import _spec as spec_from
from research.dataset.checks import near_duplicate
from research.dataset.fixes import SUBSCRIPTION_VENDORS
from research.dataset.rerender import read_prompt
from research.dataset.templates import Spec, UserData
from research.dataset.users import gender_of, remove_user, seed_user
from research.dataset.words import WordsError, _catalogue, _rows

RAW_DIR = build.RAW_DIR / "batch5" / "kinds"
PLAN_FILE = RAW_DIR / "plan.json"
JOBS_FILE = RAW_DIR / "jobs.jsonl"
REVIEWED = RAW_DIR / "reviewed.json"
DATA_DIR = build.DATA_DIR / "batch5"
SEED = "fyp-dataset/batch5-kinds"
LANGUAGES = ("arabizi", "arabizi", "english")  # the 3 versions: 2 Arabizi or mixed (the first may be mixed), 1 English

SO_FAR_WORDS = ("la hala2", "la halla2", "la hadit hala2", "la hadit halla2", "so far", "until now", "sar masroufe",
                "sert", "seret", "soret", "serit", "mn awal el shaher", "men awal el shaher")  # fmt: skip
PLACES = {"restaurants": ("Dining", batch3.RESTAURANT_WORDS), "supermarkets": ("Groceries", batch3.SUPERMARKET_WORDS)}


def _period(data: UserData, kind: str, rng: random.Random) -> periods.Period | None:
    p = batch3.period_named(data, kind, rng)
    return p if p.start is None or data.receipts_in(p) else None


def _not_bills(data: UserData) -> str:
    theirs = [name for name in SUBSCRIPTION_VENDORS if name in data.shops]
    listed = ", ".join(t.quoted(name) for name in theirs)
    return "category <> 'Utilities'" + (f" AND vendor NOT IN ({listed})" if theirs else "")


def _is_bill_shop(data: UserData, name: str) -> bool:
    return data.shop(name).kind == "utility" or name in SUBSCRIPTION_VENDORS


# --- the kinds ---


def list_shops(data: UserData, rng: random.Random, kind: str, scope: str) -> Spec | None:
    p = _period(data, kind, rng)
    if p is None:
        return None
    if scope == "any":
        target = (f"SELECT vendor, currency, SUM(total) AS total_spent, SUM(total_usd) AS total_spent_usd FROM receipts"
                  f"{t._where(p.sql)} GROUP BY vendor, currency ORDER BY total_spent_usd DESC")  # fmt: skip
        return t._spec("N1", f"Every shop the user spent at, each with its total, most first (a list, not only the "
                       f"top one), {p.description}.", target, p, scope=scope)  # fmt: skip
    category, words = PLACES[scope]
    if not any(r.category == category for r in data.receipts_in(p)):
        return None
    target = (f"SELECT vendor, currency, SUM(amount) AS total_spent, SUM(amount_usd) AS total_spent_usd FROM "
              f"category_spending{t._where(f'category = {t.quoted(category)}', p.sql)} GROUP BY vendor, currency "
              "ORDER BY total_spent_usd DESC")  # fmt: skip
    return t._spec("N1", f"Every one of the user's {scope} they went to, each with its total, most first (a list, not "
                   f"only the top one), {p.description}.", target, p, words, scope=scope)  # fmt: skip


def visited_places(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    p = _period(data, kind, rng)
    if p is None:
        return None
    target = (f"SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM category_spending"
              f"{t._where(_not_bills(data), p.sql)} GROUP BY vendor ORDER BY visits DESC")
    return t._spec("N2", f"The places the user went to, ranked by how many times (visits, not money), most first, "
                   f"{p.description}.", target, p)  # fmt: skip


def bought_at(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    p = _period(data, kind, rng)
    if p is None:
        return None
    shops = sorted({r.shop for r in data.receipts_in(p) if r.lines and not _is_bill_shop(data, r.shop)})
    if not shops:
        return None
    shop = data.shop(rng.choice(shops))
    target = (f"SELECT receipt_date, item_name, currency, line_total FROM purchases"
              f"{t._where(f'vendor = {t.quoted(shop.name)}', p.sql)} ORDER BY receipt_date")
    return t._spec("N3", f"What the user bought at {shop.name}, item by item, {p.description}.", target, p,
                   t.shop_words(shop), shop=shop.name)  # fmt: skip


def top_items(data: UserData, rng: random.Random, kind: str, n: int) -> Spec | None:
    p = _period(data, kind, rng)
    if p is None:
        return None
    target = (f"SELECT item_name, SUM(line_total_usd) AS total_spent_usd FROM purchases{t._where(p.sql)} "
              f"GROUP BY item_name ORDER BY total_spent_usd DESC LIMIT {n}")
    return t._spec("N4", f"The {n} items the user spent the most money on, {p.description}.", target, p,
                   _number_words(n), top=n)  # fmt: skip


def _number_words(n: int) -> tuple[str, ...]:
    return {1: (), 3: ("3", "three", "tlete", "tleteh"), 5: ("5", "five", "khamse", "khamsa")}[n]


def items_by_price(data: UserData, rng: random.Random, kind: str, n: int, dearest: bool, scope: str) -> Spec | None:
    p = _period(data, kind, rng)
    if p is None:
        return None
    condition, words, what = "", (), "items"
    if scope == "supermarket":
        condition, words, what = "category = 'Groceries'", batch3.SUPERMARKET_WORDS, "supermarket items (Groceries)"
    elif scope == "group":
        groups = sorted({data.catalogue.item(line.item).group for r in data.receipts_in(p) for line in r.lines}
                        - {None} & set(data.catalogue.group_words))  # fmt: skip
        if not groups:
            return None
        group = rng.choice(groups)
        names = sorted(n_ for n_ in data.items if data.catalogue.item(n_).group == group)
        condition, words, what = t.items_in(names), data.catalogue.group_words[group], f"{group} (a kind of product)"
    order, extreme = ("DESC", "MAX") if dearest else ("ASC", "MIN")
    target = (f"SELECT item_name, {extreme}(line_total_usd / quantity) AS price_usd FROM purchases"
              f"{t._where(condition, p.sql)} GROUP BY item_name ORDER BY price_usd {order} LIMIT {n}")
    which = "priciest" if dearest else "cheapest"
    return t._spec("N5", f"The {n} {which} {what} the user bought, by price per unit, {p.description}.", target, p,
                   words, _number_words(n), (("aghla", "most expensive", "priciest", "a8la") if dearest else
                                             ("arkhas", "cheapest", "arkhas shi")), top=n, dearest=dearest,
                   scope=scope)  # fmt: skip


def biggest_receipt(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    p = _period(data, kind, rng)
    if p is None:
        return None
    target = (f"SELECT receipt_date, vendor, currency, total, total_usd FROM receipts{t._where(p.sql)} "
              "ORDER BY total_usd DESC LIMIT 1")
    return t._spec("N6", f"The user's biggest receipt (the highest total), with its shop and date, {p.description}.",
                   target, p, ("fatoura", "fetoura", "receipt", "fawatir", "fwatir", "fwatire", "fawatire", "fatourit"))  # fmt: skip


def two_months(data: UserData, rng: random.Random, what: str) -> Spec | None:
    """One item, shop or category, this month vs last month (as T17's months, filtered on it)."""
    first, second = (batch3.period_named(data, kind, rng) for kind in ("last_month", "this_month"))  # her spellings too
    span = ("receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' "
            "AND receipt_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'")
    bought = [r for r in data.user.receipts if first.start <= r.day < second.end]
    if what == "item":
        names = sorted({line.item for r in bought for line in r.lines})
        if not names:
            return None
        name = rng.choice(names)
        view, amount, condition = "purchases", "line_total", t.item_is(name)
        words, label = t.item_words(data.catalogue.item(name)), {"item": name}
    elif what == "shop":
        names = sorted({r.shop for r in bought if not _is_bill_shop(data, r.shop)})
        if not names:
            return None
        name = rng.choice(names)
        view, amount, condition = "receipts", "total", f"vendor = {t.quoted(name)}"
        words, label = t.shop_words(data.shop(name)), {"shop": name}
    else:
        shared = set(data.catalogue.default_categories) | set(data.user.private_categories)
        names = sorted({line.category or r.category for r in bought for line in r.lines} & shared)
        if not names:
            return None
        name = rng.choice(names)
        view, amount, condition = "category_spending", "amount", f"category = {t.quoted(name)}"
        words, label = t.category_words(data.catalogue, name), {"category": name}
    target = (f"SELECT date_trunc('month', receipt_date) AS month, currency, SUM({amount}) AS total_spent, "
              f"SUM({amount}_usd) AS total_spent_usd FROM {view}{t._where(condition, span)} "
              "GROUP BY month, currency ORDER BY month, currency")  # fmt: skip
    return Spec("N7", "sql", f"Whether the user spent more on {name} {first.description} or {second.description}.",
                target, (words, first.words, second.words), labels={"period": "last_month+this_month", **label,
                                                                    "compared": what})  # fmt: skip


def per_visit(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    p = _period(data, kind, rng)
    if p is None:
        return None
    visits = Counter(r.shop for r in data.receipts_in(p) if not _is_bill_shop(data, r.shop))
    shops = sorted(s for s, n in visits.items() if n >= 2)
    if not shops:
        return None
    shop = data.shop(rng.choice(shops))
    target = (f"SELECT currency, ROUND(AVG(total), 2) AS average_per_visit, ROUND(AVG(total_usd), 2) AS "
              f"average_per_visit_usd, COUNT(*) AS visits FROM receipts{t._where(f'vendor = {t.quoted(shop.name)}', p.sql)} "
              "GROUP BY currency")  # fmt: skip
    return t._spec("N8", f"How much the user usually pays per visit at {shop.name} (the average receipt), "
                   f"{p.description}.", target, p, t.shop_words(shop), shop=shop.name)  # fmt: skip


def so_far(data: UserData, rng: random.Random) -> Spec | None:
    p = batch3.period_named(data, "this_month", rng)  # her spellings too
    if not data.receipts_in(p):
        return None
    return t._spec("N10", "How much the user has spent this month so far (the month is not over yet).",
                   t.money("receipts", "total", p.sql), p, SO_FAR_WORDS)


def different_shops(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    p = _period(data, kind, rng)
    if p is None:
        return None
    target = f"SELECT COUNT(DISTINCT vendor) AS shops FROM category_spending{t._where(_not_bills(data), p.sql)}"
    return t._spec("N9", f"How many different shops or places the user went to (not visits: different places), "
                   f"{p.description}.", target, p)  # fmt: skip


def unknown_shop(data: UserData, rng: random.Random, asked: str) -> Spec | None:
    """N3 / N8 at a shop the user never went to: the stored "no receipts from X" question back (C2)."""
    missing = [s for s in data.catalogue.shops if s.name not in data.shops and s.kind != "utility"]
    if not missing:
        return None
    shop = rng.choice(missing)
    same_kind = sorted(s for s in data.shops if data.shop(s).kind == shop.kind)
    suggestion = same_kind[0] if same_kind else None
    what = "what the user bought at" if asked == "bought" else "how much the user usually pays per visit at"
    hint = f"Say they have no receipts from {shop.name}" + (f" and ask whether they mean {suggestion}." if suggestion
                                                             else " and ask which shop they mean.")  # fmt: skip
    return Spec("C2", "clarify", f"Asks {what} {shop.name}, where they have no receipts.", None,
                (t.shop_words(shop),), hint, labels={"shop": shop.name, "suggestion": suggestion, "asked": asked})


# (maker, args, train count); the validation users get one of each kind in KINDS_IN_VALIDATION.
WANTS = (
    (list_shops, ("this_month", "any"), 2), (list_shops, ("last_month", "any"), 2), (list_shops, ("last_week", "any"), 1),
    (list_shops, ("this_month", "restaurants"), 2), (list_shops, ("last_month", "restaurants"), 2),
    (list_shops, ("since_start_of_year", "restaurants"), 1), (list_shops, ("this_month", "supermarkets"), 2),
    (list_shops, ("last_month", "supermarkets"), 1),
    (visited_places, ("this_month",), 2), (visited_places, ("since_start_of_year",), 2),
    (bought_at, ("last_week",), 3), (bought_at, ("this_month",), 3), (bought_at, ("last_month",), 3),
    (top_items, ("this_month", 3), 3), (top_items, ("last_month", 5), 2), (top_items, ("since_start_of_year", 5), 2),
    (top_items, ("this_week", 3), 1),
    (items_by_price, ("this_month", 1, True, "all"), 2), (items_by_price, ("last_month", 3, True, "all"), 1),
    (items_by_price, ("since_start_of_year", 5, True, "all"), 1), (items_by_price, ("this_month", 3, False, "supermarket"), 2),
    (items_by_price, ("since_start_of_year", 5, False, "group"), 2),
    (biggest_receipt, ("this_month",), 2), (biggest_receipt, ("last_month",), 2), (biggest_receipt, ("since_start_of_year",), 2),
    (two_months, ("item",), 3), (two_months, ("shop",), 3), (two_months, ("category",), 3),
    (per_visit, ("none",), 4), (per_visit, ("since_start_of_year",), 3),
    (so_far, (), 8),
    (different_shops, ("this_month",), 2), (different_shops, ("last_month",), 2),
    (unknown_shop, ("bought",), 3), (unknown_shop, ("visit",), 3),
)  # fmt: skip
KINDS_IN_VALIDATION = (list_shops, visited_places, bought_at, top_items, items_by_price, biggest_receipt, two_months,
                       per_visit, so_far, different_shops, unknown_shop)  # fmt: skip


def users() -> list[tuple[int, str, UserData]]:
    found = []
    for module, load, user in ((batch3, batch3.load_batch3_catalogue, batch3.batch3_user),
                               (batch4, batch4.load_batch4_catalogue, batch4.batch4_user)):  # fmt: skip
        catalogue = load()
        for split, numbers in (("train", module.TRAIN), ("validation", module.VALIDATION)):
            found += [(number, split, user(number, catalogue)) for number in numbers]
    return found


def plan() -> list[dict]:
    """Every wanted spec, given to the users of its split in turn (a user who cannot make one passes it on)."""
    everyone = users()
    jobs, seen = [], set()
    for split in ("train", "validation"):
        pool = [(n, d) for n, s, d in everyone if s == split]
        wants = WANTS if split == "train" else [next(w for w in WANTS if w[0] is maker) + () for maker in
                                                KINDS_IN_VALIDATION]  # fmt: skip
        turn = 0
        for index, (maker, args, count) in enumerate(wants):
            for copy in range(count if split == "train" else 1):
                for attempt in range(len(pool) * 3):
                    number, data = pool[(turn + attempt) % len(pool)]
                    rng = random.Random(f"{SEED}/{split}/{index}/{copy}/{attempt}")
                    spec = maker(data, rng, *args)
                    key = (number, spec.target, spec.description) if spec else None
                    if spec is not None and key not in seen:
                        seen.add(key)
                        jobs.append({"job_id": f"k-{split[0]}-{len(jobs)}", "user": number, "split": split,
                                     "today": data.today.isoformat(), "spec": asdict(spec)})
                        break
                else:
                    raise WordsError(f"{split}: no user can make {maker.__name__}{args}")
                turn += 1
    return jobs


def prepare(jobs_file: Path = JOBS_FILE) -> list[dict]:
    jobs = plan()
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    data = {number: d for number, _, d in users()}
    for number in sorted({job["user"] for job in jobs}):
        user = data[number].user
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                for job in (j for j in jobs if j["user"] == number):
                    job["names"] = asdict(names)
                    if job["spec"]["kind"] == "sql":
                        sql = rules.prepare(guard.check(job["spec"]["target"]), names, user.today)
                        job["rows"] = _rows(services.assistant.run_query(user_id, sql))
                    else:
                        job["rows"] = None
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(job, ensure_ascii=False) + "\n" for job in jobs), encoding="utf-8")
    return jobs


# --- replay ---


def _reply(job: dict, spec: Spec, version: dict) -> str:
    if spec.kind == "sql":
        return spec.target
    from research.dataset.checks import Version  # noqa: PLC0415
    from research.dataset.replies import users_reply  # noqa: PLC0415

    if version["language"] == "english":
        return version["reply"]
    rng = random.Random(f"{SEED}/replies/{job['job_id']}/{version['question']}")
    return users_reply(Version(version["language"], version["question"], "CLARIFY: -"), spec, _catalogue(job["user"]),
                       rng).reply  # fmt: skip


def _check_version(job: dict, version: dict, spec: Spec, reply: str) -> None:
    """The stored questions' checks, with the reply a question back gets (a CLARIFY is checked with it)."""
    from research.dataset.checks import Version, problems  # noqa: PLC0415

    found = problems(Version(version["language"], version["question"], None if spec.kind == "sql" else reply), spec,
                     _catalogue(job["user"]))  # fmt: skip
    found += [f"rejected spelling {word!r}" for word in REJECTED if re.search(rf"(?<!\w){re.escape(word)}(?!\w)",
                                                                             version["question"], re.IGNORECASE)]
    if found:
        raise WordsError(f"{job['job_id']}: {version['question']!r}: {'; '.join(found)}")


def examples(jobs: list[dict], reviewed: dict[str, list[dict]]) -> list[dict]:
    if set(reviewed) != {job["job_id"] for job in jobs}:
        raise WordsError(f"reviewed {len(reviewed)} jobs, planned {len(jobs)}")
    out = []
    for job in jobs:
        spec = spec_from(job["spec"])
        for version in reviewed[job["job_id"]]:
            reply = _reply(job, spec, version)
            _check_version(job, version, spec, reply)
            labels = {**spec.labels, "template": spec.template, "kind": spec.kind, "language": version["language"],
                      "user": job["user"], "split": job["split"], "spec": job["job_id"], "result_rows": job["rows"],
                      "part": "kinds"}  # fmt: skip
            prompt = build_prompt(version["question"], UserNames(**job["names"]), date.fromisoformat(job["today"]), (),
                                  gender=gender_of(job["user"]))  # fmt: skip
            out.append({"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}],
                        "labels": labels})
    return out


def replay(reviewed_file: Path = REVIEWED, jobs_file: Path = JOBS_FILE, out_dir: Path = DATA_DIR,
           held_out: tuple[str, ...] | None = None) -> dict:  # fmt: skip
    jobs = [json.loads(line) for line in jobs_file.read_text(encoding="utf-8").splitlines()]
    if [(j["job_id"], j["spec"]) for j in jobs] != [(j["job_id"], j["spec"]) for j in json.loads(json.dumps(plan()))]:
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
        (out_dir / f"kinds_{split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                      encoding="utf-8")  # fmt: skip
    return {"train": len(out["train"]), "validation": len(out["validation"]), "near test questions, dropped": near,
            "kinds": dict(Counter(e["labels"]["template"] for rows in out.values() for e in rows))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for flag in ("--plan", "--prepare", "--replay"):
        mode.add_argument(flag, action="store_true")
    args = parser.parse_args(argv)
    if args.plan:
        jobs = plan()
        PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)
        PLAN_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
        print(len(jobs), "jobs:", dict(Counter((j["split"], j["spec"]["template"]) for j in jobs)))
    elif args.prepare:
        saved = prepare()
        print(len(saved), "jobs; empty answers:", sum(1 for j in saved if j["rows"] == 0))
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
