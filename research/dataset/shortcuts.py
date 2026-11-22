"""Batch 5: breaking two shortcuts (decided with Christina on 2026-11-22; PROGRESS.md).

    python -m research.dataset.shortcuts --plan      # -> raw/batch5/shortcuts/plan.json (the questions to write)
    python -m research.dataset.shortcuts --prepare   # seed each user, run every target as the app would -> jobs.jsonl
    python -m research.dataset.shortcuts --replay    # her reviewed versions -> data/batch5/shortcuts_{split}.jsonl

Measured in the mix (Arabizi / mixed): "ekher marra" meant the latest PRICE in 343 of 408 questions (when: 44), and
"m3adal / 3adatan / bel 3ade" meant an item's average PRICE in 396 of 426 (usual per month 14, per visit 10). So the
model reads those words as a price whatever else is said. Each question here MUST use one of those words, with
another meaning:

- ekher marra: when the last time was (B11, batch 4's builder); how much I spent the last time I went to a shop
  (L1: that latest receipt, as part 4's "last receipt from a shop"); what I bought the last time there (L2: the items
  of that receipt);
- 3adatan / m3adal / bel 3ade: how much I usually spend on an item a month (B7, batch 3's), the average receipt per
  visit at a shop (N8, part 4's), how often I go to a shop (B13, batch 4's), and the shop I usually go to most (L3:
  the most visited of all, bills and subscriptions left out).

Built on batch 3-4 users from the batches' own SQL pieces; every target is run through the app; 2 Arabizi or mixed
versions per job (the shortcuts are in Arabizi), written by agents and reviewed by her (flagged lines). The examples
are built by part 4's code (kinds.examples: the stored questions' checks, rejected spellings).
"""

import argparse
import json
import random
import tempfile
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from research.dataset import batch3, batch4, build, kinds
from research.dataset import templates as t
from research.dataset.templates import Spec, UserData
from research.dataset.users import remove_user, seed_user
from research.dataset.words import WordsError, _rows

RAW_DIR = build.RAW_DIR / "batch5" / "shortcuts"
PLAN_FILE = RAW_DIR / "plan.json"
JOBS_FILE = RAW_DIR / "jobs.jsonl"
REVIEWED = RAW_DIR / "reviewed.json"
DATA_DIR = build.DATA_DIR / "batch5"
SEED = "fyp-dataset/batch5-shortcuts"
USUALLY = ("3adatan", "aadatan", "bel 3ade", "bl 3ade", "m3adal", "usually", "on average", "normally")
LAST_TIME = batch4.LAST_TIME
# "aam jib..." is habitual (what I usually buy): with 3adatan or alone, never with ekher marra (her ruling, 2026-11-22)
HABIT = tuple(f"{a} {v}" for a in ("aam", "3am") for v in ("jib", "jibon", "jiba", "jibo", "jeeb", "jeebon", "jeeba",
                                                           "jeebo"))  # fmt: skip
USUAL_BUY = USUALLY + HABIT
NOT_GOODS = ("utility", "subscription", "taxi", "fuel", "cinema", "gym", "car_wash", "delivery")  # no goods to list


def _with(spec: Spec | None, words: tuple[str, ...]) -> Spec | None:
    """The spec, which must also say one of `words` (the shortcut word it teaches another meaning of)."""
    return replace(spec, mentions=(*spec.mentions, words)) if spec else None


def _latest_receipt(shop: str) -> str:
    return (f"SELECT receipt_id FROM receipts WHERE vendor = {t.quoted(shop)} "
            "ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1")


def last_visit_total(data: UserData, rng: random.Random) -> Spec | None:
    shops = batch4._shops(data)
    if not shops:
        return None
    shop = rng.choice(shops)
    target = (f"SELECT receipt_date, vendor, currency, total, total_usd FROM receipts WHERE vendor = {t.quoted(shop)} "
              "ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1")
    return Spec("L1", "sql", f"How much the user spent the LAST TIME they went to {shop} (that latest receipt's total, "
                "not an item's price).", target, (t.shop_words(data.shop(shop)), LAST_TIME),
                labels={"period": "none", "shop": shop})  # fmt: skip


def last_visit_items(data: UserData, rng: random.Random) -> Spec | None:
    shops = [s for s in batch4._shops(data) if any(r.shop == s and r.lines for r in data.user.receipts)]
    if not shops:
        return None
    shop = rng.choice(shops)
    target = (f"SELECT receipt_date, item_name, currency, line_total FROM purchases WHERE receipt_id = "
              f"({_latest_receipt(shop)})")
    return Spec("L2", "sql", f"What the user bought the LAST TIME they went to {shop} (the items of that latest "
                "receipt).", target, (t.shop_words(data.shop(shop)), LAST_TIME),
                labels={"period": "none", "shop": shop})  # fmt: skip


def usual_shop(data: UserData, rng: random.Random) -> Spec | None:
    target = (f"SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM category_spending"
              f"{t._where(kinds._not_bills(data))} GROUP BY vendor ORDER BY visits DESC LIMIT 1")
    return Spec("L3", "sql", "Which shop or place the user USUALLY goes to (the most visited of all their receipts, "
                "no period).", target, (USUALLY,), labels={"period": "none"})  # fmt: skip


def usual_items(data: UserData, rng: random.Random, at_shop: bool) -> Spec | None:
    """What the user usually buys (at a shop, if `at_shop`): the items on the most receipts, top 5."""
    if not at_shop:
        target = (f"SELECT item_name, COUNT(DISTINCT receipt_id) AS times FROM purchases{t._where(kinds._not_bills(data))} "
                  "GROUP BY item_name ORDER BY times DESC, item_name LIMIT 5")
        return Spec("L5", "sql", "What the user USUALLY buys (the items on the most of their receipts, top 5, bills and "
                    "subscriptions left out; no shop, no period).", target, (USUAL_BUY,), labels={"period": "none"})
    visits = Counter(r.shop for r in data.user.receipts if r.lines and not kinds._is_bill_shop(data, r.shop)
                     and data.shop(r.shop).kind not in NOT_GOODS)  # fmt: skip
    shops = sorted(s for s, n in visits.items() if n >= 3)  # one visit is not "usually"
    if not shops:
        return None
    shop = rng.choice(shops)
    target = (f"SELECT item_name, COUNT(DISTINCT receipt_id) AS times FROM purchases WHERE vendor = {t.quoted(shop)} "
              "GROUP BY item_name ORDER BY times DESC, item_name LIMIT 5")
    return Spec("L4", "sql", f"What the user USUALLY buys at {shop} (the items on the most of its receipts, top 5; not "
                "every purchase, not a price).", target, (t.shop_words(data.shop(shop)), USUAL_BUY),
                labels={"period": "none", "shop": shop})  # fmt: skip


def when_last(data, rng, at_shop):
    return batch4.last_time(data, rng, at_shop)


def usual_month(data, rng, money):
    return _with(batch3.b7_usual_per_month(data, rng, money), USUALLY)


def per_visit(data, rng):
    return _with(kinds.per_visit(data, rng, "none"), USUALLY)


def how_often(data, rng):
    return _with(batch4.how_often(data, rng), USUALLY)


# (maker, args, train count)
WANTS = ((when_last, (True,), 6), (when_last, (False,), 6), (last_visit_total, (), 12), (last_visit_items, (), 10),
         (usual_month, (True,), 7), (usual_month, (False,), 3), (per_visit, (), 10), (how_often, (), 10),
         (usual_shop, (), 6))  # fmt: skip
# Added after her review (2026-11-22): what I usually buy ("aam jibon 3adatan", or "aam jib" alone)
USUAL_BUY_WANTS = {"train": ((usual_items, (True,), 10), (usual_items, (False,), 3)),
                   "validation": ((usual_items, (True,), 1),)}


def _add(jobs: list[dict], seen: set, split: str, pool: list, wants: tuple, prefix: str, seed: str) -> None:
    turn = 0
    for index, (maker, args, count) in enumerate(wants):
        for copy in range(count):
            for attempt in range(len(pool) * 3):
                number, data = pool[(turn + attempt) % len(pool)]
                spec = maker(data, random.Random(f"{seed}/{split}/{index}/{copy}/{attempt}"), *args)
                key = (number, spec.target) if spec else None
                if spec is not None and key not in seen:
                    seen.add(key)
                    jobs.append({"job_id": f"{prefix}-{split[0]}-{len(jobs)}", "user": number, "split": split,
                                 "today": data.today.isoformat(), "spec": asdict(spec)})
                    break
            else:
                raise WordsError(f"{split}: no user can make {maker.__name__}{args}")
            turn += 1


def plan() -> list[dict]:
    """Every wanted spec, given to the users of its split in turn; validation gets one of each maker. The jobs added
    after her review (what I usually buy) come last, so the reviewed jobs keep their ids."""
    everyone = kinds.users()
    jobs, seen = [], set()
    pools = {split: [(n, d) for n, s, d in everyone if s == split] for split in ("train", "validation")}
    for split, pool in pools.items():
        _add(jobs, seen, split, pool, WANTS if split == "train" else tuple((m, a, 1) for m, a, _ in WANTS[::2]), "s", SEED)
    for split, pool in pools.items():
        _add(jobs, seen, split, pool, USUAL_BUY_WANTS[split], "u", f"{SEED}/usual-buy")
    return jobs


def prepare(jobs_file: Path = JOBS_FILE) -> list[dict]:
    jobs = plan()
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    data = {n: d for n, _, d in kinds.users()}
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
                        guard.check(job["spec"]["target"]), names, user.today)))  # fmt: skip
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs), encoding="utf-8")
    return jobs


def replay(reviewed_file: Path = REVIEWED, jobs_file: Path = JOBS_FILE, out_dir: Path = DATA_DIR) -> dict:
    jobs = [json.loads(line) for line in jobs_file.read_text(encoding="utf-8").splitlines()]
    if [(j["job_id"], j["spec"]) for j in jobs] != [(j["job_id"], j["spec"]) for j in json.loads(json.dumps(plan()))]:
        raise WordsError("the saved jobs are not the plan: prepare again")
    found = kinds.examples(jobs, json.loads(reviewed_file.read_text(encoding="utf-8")))
    held_out = build.test_questions(None)
    from research.dataset.checks import near_duplicate  # noqa: PLC0415
    from research.dataset.rerender import read_prompt  # noqa: PLC0415

    out, near = {"train": [], "validation": []}, 0
    for example in found:
        example["labels"]["part"] = "shortcuts"
        if near_duplicate(read_prompt(example["messages"][0]["content"]).question, held_out):
            near += 1
            continue
        out[example["labels"]["split"]].append(example)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in out.items():
        (out_dir / f"shortcuts_{split}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
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
