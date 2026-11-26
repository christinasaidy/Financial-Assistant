"""Batch 5: "not what I meant", with what they did mean (decided with Christina on 2026-11-22; PROGRESS.md).

    python -m research.dataset.corrections --plan      # -> raw/batch5/corrections/plan.json (the chats to write)
    python -m research.dataset.corrections --prepare   # seed each user, run the corrected SQL as the app would
    python -m research.dataset.corrections --replay    # -> data/batch5/corrections_{split}.jsonl

Batch 1's "ma fhemet" / "la2 msh hek azde" lines (C6) only say they did not understand. People also say what they
meant ("la2 msh hek azdi, azdi el feta bas"):

- K1 (20), in a chat: a reviewed batch 3-4 question and its answer, then the user says it is not what they meant and
  names another item or shop (as part 1's D), another period, the other measure (times / money), or one category of
  a total. The answer is the corrected SQL, built from the first question's own pieces (batch5._target), so it looks
  exactly like a standalone one.
- K2 (10), alone with nothing earlier: "not what I meant" with a still-vague explanation ("ma fhemet, azdi el masrouf
  msh el fwatir") -> the C6 question back ("shu baddak ta3ref bel zabt?"; the mix gives each user their form).

Her reviewed lines are in raw/batch5/corrections/reviewed.json. Nothing is written unless every line passes its checks.
"""

import argparse
import json
import random
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

from app.domain.assistant.prompt import Exchange, UserNames, build_prompt

from research.dataset import batch5, build, deciding, periods, smalltalk
from research.dataset.batch5 import _bought, _confused_item, _is_bill, _item_name, _measure, _shop_name, _sibling_shop
from research.dataset.batch5 import _target as target
from research.dataset.checks import near_duplicate
from research.dataset.genders import FORMS
from research.dataset.rerender import read_prompt
from research.dataset.templates import item_is, money, quoted
from research.dataset.users import gender_of, remove_user, seed_user

RAW_DIR = build.RAW_DIR / "batch5" / "corrections"
PLAN_FILE = RAW_DIR / "plan.json"
JOBS_FILE = RAW_DIR / "jobs.jsonl"
REVIEWED = RAW_DIR / "reviewed.json"
DATA_DIR = build.DATA_DIR / "batch5"
SEED = "fyp-dataset/batch5-corrections"
# What each chat corrects, in turn (train 20, validation 2). Shops: only 2 stored questions have a shop of the same
# kind the user also went to in that period, so 2. No validation user allows an item correction. The last train item
# is her "X msh Y" line, the next her "ma azde hek" (2026-11-22).
KINDS = {"train": ("item", "shop", "period", "times", "money", "item", "shop", "period", "times", "money", "category",
                   "item", "item", "period", "times", "money", "category", "period", "item", "period"),
         "validation": ("period", "money")}  # fmt: skip
NOT_WHAT_I_MEANT = FORMS[2].man  # "CLARIFY: shu baddak ta3ref bel zabt?"
ENGLISH_NOT_WHAT_I_MEANT = "CLARIFY: What exactly would you like to know?"


class CorrectionError(ValueError):
    """A reviewed line that does not match the plan, or fails a check."""


def _period(data, first, rng):
    """Another period: this month or last month (one the user bought in), or this month when the first had none."""
    choices = [p for p in (periods.this_month(data.today), periods.last_month(data.today)) if p.sql != first.period]
    name = _item_name(first.what) or _shop_name(first.what)
    bought = [p for p in choices if not name or _bought(data, p, name)]
    return rng.choice(bought) if bought else None


def _correction(kind: str, data, first, rng: random.Random) -> dict | None:
    measure = _measure(first)
    item, shop = _item_name(first.what), _shop_name(first.what)
    if kind in ("item", "shop"):
        if (kind == "item") != bool(item) or (kind == "shop" and not shop):
            return None
        other = _confused_item(data, item, rng, first.dates) if item else _sibling_shop(data, shop, rng, first.dates)
        if other is None or not _bought(data, first.dates, other):
            return None
        what = item_is(other) if item else f"vendor = {quoted(other)}"
        return {"description": f"Not what they meant: they meant {other}, the rest the same.",
                "target": target(first.view, measure, what, first.period), "labels": {"correction": kind,
                                                                                      "other": other}}  # fmt: skip
    if kind == "period":
        if not first.what:
            return None
        p = _period(data, first, rng)
        if p is None:
            return None
        return {"description": f"Not what they meant: they meant {p.description}, the rest the same.",
                "target": target(first.view, measure, first.what, p.sql),
                "labels": {"correction": "period", "period": p.kind}}  # fmt: skip
    if kind in ("times", "money"):
        if measure == kind or not first.what or (kind == "times" and _is_bill(data, item or shop)):
            return None
        said = "how many times, not how much" if kind == "times" else "how much, not how many times"
        return {"description": f"Not what they meant: they meant {said}, the rest the same.",
                "target": target(first.view, kind, first.what, first.period), "labels": {"correction": kind}}
    if kind == "category":
        if first.template != "T1" or first.dates is None:
            return None
        spent = sorted({r.category for r in data.receipts_in(first.dates)} & set(data.categories) - {
            "Uncategorized", "Tax, discounts & rounding"})  # fmt: skip
        if not spent:
            return None
        category = rng.choice(spent)
        return {"description": f"Not what they meant: only the category {category}, the same period.",
                "target": money("category_spending", "amount", f"category = {quoted(category)}", first.period),
                "labels": {"correction": "category", "other": category}}  # fmt: skip
    raise ValueError(kind)


def plan(stored=None) -> list[dict]:
    """The K1 chats: each on a different user in turn, on a stored question with an Arabizi or mixed version."""
    stored = stored or batch5.load_stored()
    jobs = []
    for split, users in (("train", batch5.TRAIN), ("validation", batch5.VALIDATION)):
        rng = random.Random(f"{SEED}/{split}")
        turn = 0
        for index, kind in enumerate(KINDS[split]):
            job = None
            for _ in range(len(users) * 3):
                number = users[turn % len(users)]
                turn += 1
                data = batch5.user_data(number)
                firsts = [s for s in stored[number] if batch5._usable(s) and any(
                    lang != "english" for lang, _ in s.versions) and not any(j["first_spec"] == s.spec for j in jobs)]
                rng.shuffle(firsts)
                for first in firsts:
                    found = _correction(kind, data, first, rng)
                    if found:
                        language, question = next(v for v in first.versions if v[0] != "english")
                        job = {"job_id": f"k1-{split[0]}-{index}", "user": number, "split": split, "kind": kind,
                               "first_spec": first.spec, "first_language": language, "first_question": question,
                               "first_reply": first.target, "today": data.today.isoformat(), **found}
                        break
                if job:
                    break
            if job is None:
                raise CorrectionError(f"{split}: no question allows a {kind} correction")
            jobs.append(job)
    return jobs


def prepare(jobs_file: Path = JOBS_FILE) -> list[dict]:
    """The plan with each corrected SQL run through the app on its seeded user (removed after), and the user's names."""
    jobs = plan()
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    saved = []
    for number in sorted({job["user"] for job in jobs}):
        user = batch5.user_data(number).user
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                for job in (j for j in jobs if j["user"] == number):
                    result = services.assistant.run_query(user_id, rules.prepare(guard.check(job["target"]), names,
                                                                                 user.today))  # fmt: skip
                    saved.append({**job, "rows": sum(1 for row in result.rows if any(v not in (None, 0) for v in row))})
            finally:
                remove_user(services, user_id)
    saved.sort(key=lambda j: [x["job_id"] for x in jobs].index(j["job_id"]))
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in saved), encoding="utf-8")
    return saved


def _stored_row(first_spec: str, question: str, data_dir: Path) -> dict:
    for batch in ("batch3", "batch4"):
        for split in ("train", "validation"):
            for line in (data_dir / batch / f"{split}.jsonl").read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row["labels"]["spec"] == first_spec and read_prompt(row["messages"][0]["content"]).question == question:
                    return row
    raise CorrectionError(f"no stored example for {first_spec}: {question!r}")


def chat_examples(jobs: list[dict], reviewed: dict, data_dir: Path) -> list[dict]:
    lines = {line["job_id"]: line for line in reviewed["K1"]}
    if set(lines) != {j["job_id"] for j in jobs}:
        raise CorrectionError(f"reviewed K1 lines {sorted(lines)} are not the planned chats")
    out = []
    for job in jobs:
        line = lines[job["job_id"]]
        smalltalk._check_line(job["job_id"], line["language"], line["question"], job["target"])
        first = _stored_row(job["first_spec"], job["first_question"], data_dir)
        parts = read_prompt(first["messages"][0]["content"])
        history = (Exchange(job["first_question"], first["messages"][1]["content"]),)
        prompt = build_prompt(line["question"], parts.names, date.fromisoformat(job["today"]), history,
                              gender=gender_of(job["user"]))  # fmt: skip
        labels = {"template": "K1", "kind": "sql", "language": line["language"], "user": job["user"],
                  "split": job["split"], "spec": job["job_id"], "result_rows": job["rows"], "history": 1,
                  "history_role": "dependent", "first_spec": job["first_spec"], "part": "corrections",
                  **{k: v for k, v in job["labels"].items() if isinstance(v, str)}}  # fmt: skip
        out.append({"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": job["target"]}],
                    "labels": labels})
    return out


def alone_examples(reviewed: dict, pools) -> list[dict]:
    taken, out = Counter(), []
    for line in reviewed["K2"]:
        row = deciding._on_user(pools, line, taken)
        reply = ENGLISH_NOT_WHAT_I_MEANT if line["language"] == "english" else NOT_WHAT_I_MEANT
        smalltalk._check_line(f"k2-{line['n']}", line["language"], line["question"], reply)
        parts = read_prompt(row["messages"][0]["content"])
        labels = {"template": "C6", "kind": "clarify", "language": line["language"], "user": row["labels"]["user"],
                  "split": row["labels"]["split"], "spec": f"k2-{line['n']}", "result_rows": None,
                  "part": "corrections"}  # fmt: skip
        out.append(deciding._example(line["question"], parts.names, parts.today, row["labels"]["user"], reply, labels))
    return out


def replay(reviewed_file: Path = REVIEWED, jobs_file: Path = JOBS_FILE, out_dir: Path = DATA_DIR,
           data_dir: Path = build.DATA_DIR, held_out: tuple[str, ...] | None = None) -> dict:  # fmt: skip
    reviewed = json.loads(reviewed_file.read_text(encoding="utf-8"))
    jobs = [json.loads(line) for line in jobs_file.read_text(encoding="utf-8").splitlines()]
    planned = plan()
    if [(j["job_id"], j["first_spec"], j["target"]) for j in jobs] != [
            (j["job_id"], j["first_spec"], j["target"]) for j in planned]:  # fmt: skip
        raise CorrectionError("the saved jobs are not the plan: prepare again")
    examples = chat_examples(jobs, reviewed, data_dir) + alone_examples(reviewed, deciding.context_rows(data_dir))
    held_out = build.test_questions(None) if held_out is None else held_out
    out, near = {"train": [], "validation": []}, 0
    for example in examples:
        if near_duplicate(read_prompt(example["messages"][0]["content"]).question, held_out):
            near += 1
            continue
        out[example["labels"]["split"]].append(example)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, found in out.items():
        (out_dir / f"corrections_{split}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in found), encoding="utf-8")
    return {"train": len(out["train"]), "validation": len(out["validation"]), "near test questions, dropped": near,
            "kinds": dict(Counter(e["labels"]["template"] for found in out.values() for e in found))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    if args.plan:
        jobs = plan()
        PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)
        PLAN_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
        print(len(jobs), "chats:", dict(Counter((j["split"], j["kind"]) for j in jobs)))
    elif args.prepare:
        saved = prepare()
        print(len(saved), "chats; empty answers:", sum(1 for j in saved if j["rows"] == 0))
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
