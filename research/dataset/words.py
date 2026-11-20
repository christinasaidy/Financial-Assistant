"""Batch 5 part 5: everyday words (decided with Christina on 2026-11-20; agent_documentation/PROGRESS.md).

    python -m research.dataset.words --prepare   # plan the abel mbereh questions, seed each user, run every SQL
    python -m research.dataset.words --replay    # the written versions -> data/batch5/words_{train,validation}.jsonl

Two sets, both written by the assistant and reviewed by Christina:

- matra7 / matrah ("place"; plurals amekin, matare7, matareh): new versions of stored batch 2-4 questions
  (raw/batch5/words/matra7.json). Each keeps its stored question's gold reply and result; only the user's wording
  is new, so no SQL runs again. The existing versions stay as they are.
- abel mbereh (the day before yesterday; also 2abel mbereh, awalt mbereh): one new question per batch 1-4 user who
  bought something that day, the six kinds in turn (total, item, top shop, what was bought, visits, category), and
  three for users who bought nothing then (an empty day), built from the batches' own SQL pieces with the
  day-before-yesterday period. Prepare seeds each user, runs every target through the app's guard, answering
  rules and read-only role, and always removes the user (raw/batch5/words/day_before_jobs.jsonl). The versions are
  in raw/batch5/words/day_before.json.

Nothing is written unless every version passes the stored questions' checks (checks.problems: its words, no Arabic
script, length) and has no rejected spelling; a version near a test question is dropped and counted, never shown.
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

from research.dataset import answers_build, batch3, batch4, build, periods
from research.dataset import templates as t
from research.dataset.batch2_build import _spec
from research.dataset.checks import Version, near_duplicate, problems
from research.dataset.rerender import read_prompt
from research.dataset.templates import Spec, UserData
from research.dataset.users import gender_of, make_user, remove_user, seed_user

RAW_DIR = build.RAW_DIR / "batch5" / "words"
MATRA7_FILE = RAW_DIR / "matra7.json"
JOBS_FILE = RAW_DIR / "day_before_jobs.jsonl"
DAY_BEFORE_FILE = RAW_DIR / "day_before.json"
DATA_DIR = build.DATA_DIR / "batch5"
SEED = "fyp-dataset/batch5-words"
PERIOD = "day_before_yesterday"
BATCHES = {"b2": "batch2", "b3": "batch3", "b4": "batch4"}


class WordsError(ValueError):
    """The written versions do not match the plan, or one fails a check."""


def category_spend(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    """How much the user spent on one category in the period (a category bought then, else none). A line's own
    category counts first, as in the category_spending view (bread at Wooden Bakery is Groceries, not Dining); the
    receipt's is used for its lines without one, or when it has no lines."""
    p = batch3.period_named(data, kind, rng)
    shared = set(data.catalogue.default_categories) | set(data.user.private_categories)
    spent = {line.category or r.category for r in data.receipts_in(p) for line in r.lines}
    spent |= {r.category for r in data.receipts_in(p) if not r.lines}
    bought = sorted(spent & shared)
    if not bought:
        return None
    category = rng.choice(bought)
    return t._spec("T3", f"How much the user spent on the category {category}, {p.description}.",
                   t.money("category_spending", "amount", f"category = {t.quoted(category)}", p.sql), p,
                   t.category_words(data.catalogue, category), category=category)  # fmt: skip


# The six kinds, in turn over the users; a user who cannot make one gets the next.
KINDS = (("total", batch3.total), ("item", batch3.item_spend), ("top shop", batch3.top_shop),
         ("bought", batch3.b1_list), ("visits", batch3.visits), ("category", category_spend))  # fmt: skip


def users() -> list[tuple[int, str, UserData]]:
    """The batch 1-4 users (31 is the test user) with their split, each with their own batch's catalogue."""
    catalogue = build.load_catalogue()
    found = [(n, "validation" if n in build.VALIDATION_USERS else "train", UserData(make_user(catalogue, n), catalogue))
             for n in range(1, build.USER_COUNT + 1)]  # fmt: skip
    for module, load, user in ((batch3, batch3.load_batch3_catalogue, batch3.batch3_user),
                               (batch4, batch4.load_batch4_catalogue, batch4.batch4_user)):  # fmt: skip
        catalogue = load()
        for split, numbers in (("train", module.TRAIN), ("validation", module.VALIDATION)):
            found += [(number, split, user(number, catalogue)) for number in numbers]
    return found


# Kinds asked of a user who bought nothing that day, so some examples show an empty day (decided 2026-11-20).
EMPTY_KINDS = ("total", "visits", "item")


def plan() -> list[dict]:
    """One day-before-yesterday spec per user who bought something that day, the kinds in turn; and one each of
    EMPTY_KINDS for the first users who bought nothing then. Deterministic."""
    jobs, busy, empty = [], 0, 0
    makers = dict(KINDS)
    for number, split, data in users():
        rng = random.Random(f"{SEED}/{number}")
        if data.receipts_in(periods.day_before_yesterday(data.today)):
            options = [KINDS[(busy + step) % len(KINDS)] for step in range(len(KINDS))]
            busy += 1
        elif empty < len(EMPTY_KINDS):
            options = [(EMPTY_KINDS[empty], makers[EMPTY_KINDS[empty]])]
            empty += 1
        else:
            continue
        for kind, maker in options:
            spec = maker(data, rng, PERIOD)
            if spec is not None:
                jobs.append({"job_id": f"w-{number}", "user": number, "split": split, "kind": kind,
                             "today": data.today.isoformat(), "spec": asdict(spec)})
                break
    return jobs


def _rows(result) -> int:
    return sum(1 for row in result.rows if any(value not in (None, 0) for value in row))


def prepare(jobs_file: Path = JOBS_FILE) -> list[dict]:
    jobs = plan()
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    data = {number: d for number, _, d in users()}
    for job in jobs:
        user = data[job["user"]].user
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                sql = rules.prepare(guard.check(job["spec"]["target"]), names, user.today)
                job["rows"] = _rows(services.assistant.run_query(user_id, sql))
                job["names"] = asdict(names)
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(job, ensure_ascii=False) + "\n" for job in jobs), encoding="utf-8")
    return jobs


# --- replay ---


def _check(job_id: str, version: dict, spec: Spec, catalogue) -> None:
    found = problems(Version(version["language"], version["question"]), spec, catalogue)
    found += [f"rejected spelling {word!r}" for word in answers_build.REJECTED
              if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", version["question"], re.IGNORECASE)]
    if found:
        raise WordsError(f"{job_id}: {version['question']!r}: {'; '.join(found)}")


def _example(question: str, language: str, names: UserNames, today: date, user: int, reply: str, labels: dict
             ) -> dict:  # fmt: skip
    prompt = build_prompt(question, names, today, (), gender=gender_of(user))
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}],
            "labels": {**labels, "language": language, "part": "words"}}


def stored(data_dir: Path = build.DATA_DIR) -> dict[str, dict]:
    """The first stored example of each batch 2-4 spec (its prompt gives the names and today, its reply the SQL)."""
    found = {}
    for batch in BATCHES.values():
        for split in ("train", "validation"):
            for line in (data_dir / batch / f"{split}.jsonl").read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                found.setdefault(row["labels"]["spec"], row)
    return found


def stored_specs(raw_dir: Path = build.RAW_DIR) -> dict[str, Spec]:
    found = {}
    for batch in BATCHES.values():
        for line in (raw_dir / batch / "jobs.jsonl").read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            found[entry["spec_id"]] = _spec(entry["spec"])
    return found


def _catalogue(spec_id_or_user: str | int):
    number = spec_id_or_user if isinstance(spec_id_or_user, int) else int(spec_id_or_user.split("-")[1])
    if number in batch3.TODAYS:
        return batch3.load_batch3_catalogue()
    if number in batch4.TODAYS:
        return batch4.load_batch4_catalogue()
    return build.load_catalogue()


def matra7_examples(versions: list[dict], rows: dict[str, dict], specs: dict[str, Spec]) -> list[dict]:
    out = []
    for version in versions:
        if version["spec"] not in rows:
            raise WordsError(f"no stored example for {version['spec']}")
        row = rows[version["spec"]]
        _check(version["spec"], version, specs[version["spec"]], _catalogue(version["spec"]))
        parts = read_prompt(row["messages"][0]["content"])
        labels = {**row["labels"], "word": "matra7"}
        out.append(_example(version["question"], version["language"], parts.names, parts.today, labels["user"],
                            row["messages"][1]["content"], labels))  # fmt: skip
    return out


def day_before_examples(jobs: list[dict], written: dict[str, list[dict]]) -> list[dict]:
    if set(written) != {job["job_id"] for job in jobs}:
        raise WordsError(f"written {sorted(written)}, planned {sorted(job['job_id'] for job in jobs)}")
    out = []
    for job in jobs:
        spec = _spec(job["spec"])
        for version in written[job["job_id"]]:
            _check(job["job_id"], version, spec, _catalogue(job["user"]))
            labels = {**spec.labels, "template": spec.template, "kind": "sql", "user": job["user"],
                      "split": job["split"], "spec": job["job_id"], "result_rows": job["rows"],
                      "word": "abel mbereh"}  # fmt: skip
            out.append(_example(version["question"], version["language"], UserNames(**job["names"]),
                                date.fromisoformat(job["today"]), job["user"], spec.target, labels))  # fmt: skip
    return out


def replay(raw_dir: Path = RAW_DIR, out_dir: Path = DATA_DIR, data_dir: Path = build.DATA_DIR,
           stored_raw: Path = build.RAW_DIR, held_out: tuple[str, ...] | None = None) -> dict:  # fmt: skip
    """Both sets as examples. Refuses (WordsError) before writing anything if a version fails a check."""
    jobs = [json.loads(line) for line in (raw_dir / JOBS_FILE.name).read_text(encoding="utf-8").splitlines()]
    examples = matra7_examples(json.loads((raw_dir / MATRA7_FILE.name).read_text(encoding="utf-8")),
                               stored(data_dir), stored_specs(stored_raw))  # fmt: skip
    examples += day_before_examples(jobs, json.loads((raw_dir / DAY_BEFORE_FILE.name).read_text(encoding="utf-8")))
    held_out = build.test_questions(None) if held_out is None else held_out
    out, near = {"train": [], "validation": []}, 0
    for example in examples:
        if near_duplicate(read_prompt(example["messages"][0]["content"]).question, held_out):
            near += 1
            continue
        out[example["labels"]["split"]].append(example)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in out.items():
        (out_dir / f"words_{split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                      encoding="utf-8")  # fmt: skip
    return {"train": len(out["train"]), "validation": len(out["validation"]), "near test questions, dropped": near,
            "words": dict(Counter(e["labels"]["word"] for rows in out.values() for e in rows))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare:
        jobs = prepare()
        print(len(jobs), "jobs:", dict(Counter(j["kind"] for j in jobs)),
              "| empty:", [j["job_id"] for j in jobs if j["rows"] == 0])  # fmt: skip
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
