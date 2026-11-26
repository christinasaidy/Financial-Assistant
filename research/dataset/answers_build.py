"""Batch 5 part 2 build: answer-sentence examples (research/dataset/answers.py has her patterns).

    python -m research.dataset.answers_build     # -> data/batch5/answers_{train,validation}.jsonl

About 1,200 training answers (and a validation share), approved 2026-11-19: stored standalone SQL questions are picked
per kind of result (each kind at least 20, then by its share of the training SQL), their SQL (with the fixes of
fixes.py) runs on the seeded user exactly as the app runs it, the app's own answer prompt is built from the result,
and her pattern is filled from it. An answer is kept only if the app's own number check accepts it; an empty result
is skipped, as the app answers it with a fixed message and never asks the model.
"""

import argparse
import json
import random
import re
import tempfile
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import sqlglot

from app.domain.assistant import answer as app_answers
from app.domain.assistant.errors import UnusableReply
from app.domain.assistant.prompt import build_answer_prompt

from research.dataset import answers, batch3, batch4, batch5, batch5_build, build
from research.dataset.catalogue import load_catalogue
from research.dataset.fixes import fixed_reply
from research.dataset.rerender import read_prompt
from research.dataset.users import gender_of, make_user, remove_user, seed_user

SOURCES = ("train.jsonl", "batch2/train.jsonl", "batch2/extras_train.jsonl", "batch3/train.jsonl",
           "batch4/train.jsonl", "validation.jsonl", "batch2/validation.jsonl", "batch2/extras_validation.jsonl",
           "batch3/validation.jsonl", "batch4/validation.jsonl")  # fmt: skip
TRAIN_ANSWERS = 1200
VALIDATION_SHARE = 0.15
LEAST_PER_KIND = 20
SPARE = 1.6  # picked per kind, as some results are empty or do not fit the pattern
SEED = "fyp-dataset/batch5-answers"
OUT_DIR = build.DATA_DIR / "batch5"


def result_kind(sql: str) -> str | None:
    try:
        return answers.layout(tuple(e.alias_or_name for e in sqlglot.parse_one(sql, read="postgres").selects))
    except sqlglot.errors.ParseError:
        return None


def candidates(data_dir: Path = build.DATA_DIR) -> list[dict]:
    """Every stored standalone SQL question with a result kind that has a pattern."""
    found = []
    for source in SOURCES:
        for line in (data_dir / source).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            labels = row["labels"]
            prompt = row["messages"][0]["content"]
            if labels["kind"] != "sql" or "Earlier in this chat:" in prompt:
                continue
            parts = read_prompt(prompt)
            sql = fixed_reply(row["messages"][1]["content"], parts.names.vendors)
            kind = result_kind(sql)
            if kind:
                found.append({"sql": sql, "kind": kind, "question": parts.question, "today": parts.today,
                              "names": parts.names, "labels": labels})  # fmt: skip
    return found


def choose(pool: list[dict], rng: random.Random) -> dict[str, list[dict]]:
    """The questions to answer, by split: each kind at least 20, then by its share, with spares."""
    by_split_kind = defaultdict(list)
    for c in pool:
        by_split_kind[(c["labels"]["split"], c["kind"])].append(c)
    train = Counter(c["kind"] for c in pool if c["labels"]["split"] == "train")
    total = sum(train.values())
    chosen = {"train": [], "validation": []}
    for kind, n in sorted(train.items()):
        quota = max(LEAST_PER_KIND, round(TRAIN_ANSWERS * n / total))
        for split, want in (("train", quota), ("validation", max(3, round(quota * VALIDATION_SHARE)))):
            options = sorted(by_split_kind[(split, kind)], key=lambda c: (c["labels"]["spec"], c["question"]))
            rng.shuffle(options)
            chosen[split] += [dict(c, quota=want) for c in options[: round(want * SPARE)]]
    return chosen


def user_data(number: int):
    if number in batch3.TODAYS or number in batch4.TODAYS:
        return batch5.user_data(number).user
    return make_user(load_catalogue(), number)


def asked_words(c: dict, catalogue) -> answers.Asked:
    labels, question = c["labels"], c["question"]
    arabizi = labels["language"] != "english"
    item = labels.get("item") or ""
    shop = labels.get("shop") or ""
    period_word = ""
    try:
        period = batch5.period_of(str(labels.get("period", "none")), c["today"], None)
    except KeyError:  # a period batch 3 made itself (e.g. the last 5 months): the answer leaves it unsaid
        period = None
    if period is not None and period.sql:
        kind = str(labels.get("period"))
        period_word = (answers.arabizi_period(kind, question, random.Random(f"{SEED}/period/{question}")) if arabizi
                       else answers.english_period(period.description))  # fmt: skip
    if arabizi and item:
        known = next((i for i in catalogue.items if i.name == item), None)
        item = answers.own_word(question, (item,) + ((known.words + known.suggested) if known else ())) or item
    known_item = next((i for i in catalogue.items if i.name == labels.get("item")), None)
    return answers.Asked(question, arabizi, gender_of(labels["user"]), item, shop, period_word,
                         bill=bool(known_item and known_item.vendors))


def answer_example(c: dict, result, receipt_ids, catalogue, rng: random.Random) -> dict | None:
    if app_answers.is_empty_result(result.rows) or result.truncated:
        return None
    asked = asked_words(c, catalogue)
    text = answers.render(c["kind"], result.columns, result.rows, asked, rng)
    if not text:
        return None
    totals = app_answers.column_totals(result.columns, result.rows)
    allowed = [*app_answers.result_numbers(result.rows), *totals.values(), *app_answers.date_numbers(c["today"]),
               Decimal(len(result.rows)), *([Decimal(len(receipt_ids))] if receipt_ids is not None else []),
               *app_answers.numbers_in(c["question"]), *app_answers.numbers_in(result.sql)]  # fmt: skip
    try:
        app_answers.check_numbers(text, allowed, "the result")
    except UnusableReply:
        return None
    prompt = build_answer_prompt(c["question"], result.columns, result.rows,
                                 {name: total for name, total in totals.items() if name.endswith("_usd")},
                                 None if receipt_ids is None else len(receipt_ids), result.truncated, c["today"],
                                 gender=asked.gender)  # fmt: skip
    labels = c["labels"]
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": text}],
            "labels": {"template": "ANSWER", "kind": "answer", "result": c["kind"], "language": labels["language"],
                       "user": labels["user"], "split": labels["split"], "spec": labels["spec"],
                       "source_template": labels["template"], "gender": asked.gender.value}}  # fmt: skip


def build_answers(out_dir: Path = OUT_DIR) -> dict:
    rng = random.Random(SEED)
    chosen = choose(candidates(), rng)
    catalogue = batch4.load_batch4_catalogue()
    settings = build.load_settings()
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    made = {"train": defaultdict(list), "validation": defaultdict(list)}
    by_user = defaultdict(list)
    for split, picks in chosen.items():
        for c in picks:
            by_user[c["labels"]["user"]].append((split, c))
    for number in sorted(by_user):
        user = user_data(number)
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                for split, c in by_user[number]:
                    if len(made[split][c["kind"]]) >= c["quota"]:
                        continue
                    prepared = rules.prepare(guard.check(c["sql"]), c["names"], c["today"])
                    result = services.assistant.run_query(user_id, prepared)
                    receipt_ids = services.assistant._sources(user_id, result.sql)  # as the app finds them
                    example = answer_example(c, result, receipt_ids, catalogue,
                                             random.Random(f"{SEED}/{c['labels']['spec']}/{c['question']}"))  # fmt: skip
                    if example:
                        made[split][c["kind"]].append(example)
            finally:
                remove_user(services, user_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for split, kinds in made.items():
        rows = [example for examples in kinds.values() for example in examples]
        (out_dir / f"answers_{split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                        encoding="utf-8")  # fmt: skip
        report[split] = {"answers": len(rows), "kinds": {k: len(v) for k, v in sorted(kinds.items())},
                         "languages": dict(Counter(r["labels"]["language"] for r in rows))}  # fmt: skip
    return report


# --- written by agents (her decision 2026-11-20: "be more close to real life"): code picks the questions and runs
# the real SQL; agents write each answer as a person would; code checks every answer before it is kept. ---

RAW_DIR = build.RAW_DIR / "batch5"
JOBS_FILE = RAW_DIR / "answer_jobs.jsonl"
PILOT_FILE = RAW_DIR / "answer_jobs_pilot.jsonl"  # the 40 approved pilot jobs (2026-11-20), kept as they were reviewed
AUTHORED_DIR = RAW_DIR / "answers_authored"
# kallefetne / kallefoune: her past forms are kalafetne / kalafoune (2026-11-20)
REJECTED = (*batch5_build.REJECTED, "sakin", "3alla2at", "el 3afu", "shtret", "3elka", "kallefetne", "kallefoune")
WINNER_KINDS = ("compare", "brands", "top shop money", "top shop visits", "categories", "top categories")
MAN_ONLY = ("sarafet", "dafa3et", "jebet", "rehet", "akalet", "3endak", "btedfa3", "trou7", "jebto", "baddak", "se3dak",
            "azdak", "elak", "fik", "masroufak", "masrufak", "masarifak", "fawatirak", "enta", "7abeb")  # fmt: skip
WOMAN_ONLY = ("sarafte", "dafa3te", "jebte", "rehte", "akalte", "3endik", "btedfa3e", "trou7i", "baddik", "se3dik",
              "azdik", "elik", "fiki", "masroufik", "masrufik", "masarifik", "fawatirik", "ente", "enti", "7abe")  # fmt: skip


def _words(text: str, words) -> list[str]:
    return [w for w in words if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text, re.IGNORECASE)]


def winner(kind: str, columns, rows) -> str | None:
    """The name the answer must give first: the cheapest (compare, brands) or the largest (the rankings, a category's
    currencies added up in USD). None when there is no single one: one row, two currencies compared, or a tie."""
    if kind not in WINNER_KINDS or len(rows) < 1:
        return None
    if kind in ("compare", "brands"):
        if len(rows) < 2 or len({r[1] for r in rows}) > 1:
            return None
        score = {}
        for r in rows:
            score[r[0]] = -Decimal(str(r[3]))
    else:
        score = defaultdict(Decimal)
        for r in rows:
            if r[0] != "Tax, discounts & rounding":
                score[r[0]] += Decimal(str(r[-1]))
    ranked = sorted(score.values(), reverse=True)
    if len(ranked) > 1 and ranked[0] == ranked[1]:
        return None
    return max(score, key=score.get)


def problems(job: dict, text: str) -> list[str]:
    """Why a written answer cannot be kept ([] when it can)."""
    found = []
    if not text.strip() or "\n" in text.strip() or len(text) > 400:
        found.append("empty, several lines or longer than 400 characters")
    try:
        app_answers.check_numbers(text, [Decimal(n) for n in job["allowed"]], "the result")
    except UnusableReply as error:
        found.append(str(error))
    best = winner(job["kind"], job["columns"], job["rows"])
    if best:
        names = {str(r[0]) for r in job["rows"]}
        at = {n: text.lower().find(n.lower()) for n in names if n.lower() in text.lower()}
        if best.lower() not in text.lower() or min(at, key=at.get).lower() != best.lower():
            found.append(f"the first name given must be {best}")
    if bad := _words(text, REJECTED):
        found.append(f"rejected spelling {bad}")
    if re.search(r"(?<![$\d.,])\d+[.,]\d+\s*(marra|marrat|times|visits?)\b", text, re.IGNORECASE):  # not "$4.85 marra"
        found.append('a fraction of a visit ("0.7 marra bel shaher" is not said, Christina 2026-11-19)')
    if job["language"] != "english":
        wrong = {"woman": MAN_ONLY, "man": WOMAN_ONLY, "not given": MAN_ONLY + WOMAN_ONLY}[job["gender"]]
        if bad := _words(text, wrong):
            found.append(f"{job['gender']}: words of the other gender {bad}")
    return found


def _cell(value) -> object:
    if value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    return value.isoformat()


def prepare_jobs(jobs_file: Path = JOBS_FILE) -> dict:
    """The questions to answer, run on their users as the app runs them: one job per result the model would be asked
    to answer (an empty result is answered by the app's fixed message; a count of 0 is not empty and is kept)."""
    rng = random.Random(SEED)
    chosen = choose(candidates(), rng)
    settings = build.load_settings()
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    jobs, per_kind = [], Counter()
    pilot = set()
    for j in _read_jobs(PILOT_FILE):  # already answered and approved: counted, never asked again
        pilot.add((j["labels"]["user"], j["question"]))
        per_kind[(j["split"], j["kind"])] += 1
    by_user = defaultdict(list)
    for split, picks in chosen.items():
        for c in picks:
            by_user[c["labels"]["user"]].append((split, c))
    for number in sorted(by_user):
        user = user_data(number)
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                for split, c in by_user[number]:
                    if per_kind[(split, c["kind"])] >= c["quota"] or (number, c["question"]) in pilot:
                        continue
                    prepared = rules.prepare(guard.check(c["sql"]), c["names"], c["today"])
                    result = services.assistant.run_query(user_id, prepared)
                    if app_answers.is_empty_result(result.rows) or result.truncated:
                        continue
                    receipt_ids = services.assistant._sources(user_id, result.sql)
                    totals = app_answers.column_totals(result.columns, result.rows)
                    gender = gender_of(c["labels"]["user"])
                    allowed = [*app_answers.result_numbers(result.rows), *totals.values(),
                               *app_answers.date_numbers(c["today"]), Decimal(len(result.rows)),
                               *([Decimal(len(receipt_ids))] if receipt_ids is not None else []),
                               *app_answers.numbers_in(c["question"]), *app_answers.numbers_in(result.sql)]  # fmt: skip
                    prompt = build_answer_prompt(c["question"], result.columns, result.rows,
                                                 {n: t for n, t in totals.items() if n.endswith("_usd")},
                                                 None if receipt_ids is None else len(receipt_ids), result.truncated,
                                                 c["today"], gender=gender)  # fmt: skip
                    per_kind[(split, c["kind"])] += 1
                    labels = c["labels"]
                    jobs.append({"job_id": f"a-{split[0]}-{len(jobs):04d}", "split": split, "kind": c["kind"],
                                 "language": labels["language"], "gender": gender.value, "question": c["question"],
                                 "columns": list(result.columns), "rows": [[_cell(v) for v in r] for r in result.rows],
                                 "allowed": sorted({str(n) for n in allowed}), "prompt": prompt,
                                 "labels": {"user": labels["user"], "spec": labels["spec"],
                                            "source_template": labels["template"]}})  # fmt: skip
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs), encoding="utf-8")
    return {"jobs": len(jobs), "by_split": dict(Counter(j["split"] for j in jobs)),
            "languages": dict(Counter(j["language"] for j in jobs))}  # fmt: skip


def _read_jobs(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def load_jobs(jobs_file: Path = JOBS_FILE, pilot_file: Path = PILOT_FILE) -> dict[str, dict]:
    return {j["job_id"]: j for j in _read_jobs(pilot_file) + _read_jobs(jobs_file)}


def check_authored(jobs: dict[str, dict], authored_dir: Path = AUTHORED_DIR) -> tuple[dict, dict]:
    """The written answers ({job_id: answer} per file) and, for each that cannot be kept, why."""
    written, bad = {}, {}
    for path in sorted(authored_dir.glob("*.json")):
        for job_id, text in json.loads(path.read_text(encoding="utf-8")).items():
            if job_id not in jobs:
                bad[job_id] = ["no such job"]
                continue
            written[job_id] = text
            if found := problems(jobs[job_id], text):
                bad[job_id] = found
    return written, bad


def replay(jobs_file: Path = JOBS_FILE, authored_dir: Path = AUTHORED_DIR, out_dir: Path = OUT_DIR) -> dict:
    """The approved written answers as training examples; an answer that fails a check is left out and reported."""
    jobs = load_jobs(jobs_file)
    written, bad = check_authored(jobs, authored_dir)
    rows = {"train": [], "validation": []}
    for job_id, text in written.items():
        if job_id in bad:
            continue
        job = jobs[job_id]
        rows[job["split"]].append({
            "messages": [{"role": "user", "content": job["prompt"]}, {"role": "assistant", "content": text}],
            "labels": {"template": "ANSWER", "kind": "answer", "result": job["kind"], "language": job["language"],
                       "user": job["labels"]["user"], "split": job["split"], "spec": job["labels"]["spec"],
                       "source_template": job["labels"]["source_template"], "gender": job["gender"],
                       "job_id": job_id}})  # fmt: skip
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, examples in rows.items():
        (out_dir / f"answers_{split}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in examples), encoding="utf-8")
    return {"kept": {s: len(r) for s, r in rows.items()}, "left_out": bad}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", help="write the answer jobs for the agents")
    parser.add_argument("--check", action="store_true", help="check the written answers, write nothing")
    parser.add_argument("--replay", action="store_true", help="written answers -> data/batch5/answers_*.jsonl")
    args = parser.parse_args(argv)
    if args.prepare:
        print(json.dumps(prepare_jobs(), indent=1))
    elif args.check:
        written, bad = check_authored(load_jobs())
        print(json.dumps({"written": len(written), "failing": bad}, indent=1, ensure_ascii=False))
    elif args.replay:
        print(json.dumps(replay(), indent=1, ensure_ascii=False))
    else:
        print(json.dumps(build_answers(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
