"""Build the fine-tuning dataset (plan approved by the user on 2026-11-05/07).

    python -m research.dataset.build                       # the free stand-in: tests the whole pipeline
    python -m research.dataset.build --model Qwen/Qwen3.8-27B --base-url URL --yes

For each synthetic user: seed them in the database through the app, take their names exactly as the app's prompt
lists them, make the things to ask, run every SQL target through the app's guard, answering rules and read-only
role, and remove the user. Then the writer phrases each thing six ways (several calls at once), every version is
checked, and one training example is written per version that passed, in chat format: the app's own prompt
(build_prompt) as the user message and the target as the reply. Users 1-27 are training, 28-30 validation.

A stand-in run writes under research/dataset/raw/ (not committed), so it can never replace the real dataset.
"""

import argparse
import json
import random
import sys
import tempfile
import threading
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.domain.assistant.conversation import clean_question
from app.domain.assistant.errors import QueryFailed, QueryRejected, UnsafeQuery
from app.domain.assistant.prompt import Exchange, UserNames, build_prompt
from app.infrastructure.sql.query_rules import SqlGlotQueryRules
from app.infrastructure.sql.sql_guard import SqlGlotGuard

from research.dataset.catalogue import load_catalogue
from research.dataset.checks import UnreadableReply, problems, read_versions
from research.dataset.generator_prompt import build_generator_prompt, load_seeds
from research.dataset.templates import Spec, UserData, make_specs
from research.dataset.users import USER_COUNT, make_user, remove_user, seed_user
from research.dataset.wiring import QuestionWriter, QwenWriter, StandInWriter
from research.evaluation.expected_model import ExpectedAnswersModel
from research.evaluation.questions import QUESTIONS_FILE
from research.evaluation.wiring import build_evaluation, load_settings

DATASET_DIR = Path(__file__).parent
DATA_DIR = DATASET_DIR / "data"
RAW_DIR = DATASET_DIR / "raw"
SPECS_PER_USER = 24
VALIDATION_USERS = range(28, USER_COUNT + 1)
WORKERS = 8  # writer calls at once; vLLM serves them together (decided 2026-11-08)


@dataclass
class Summary:
    examples: Counter = field(default_factory=Counter)  # by split
    kinds: Counter = field(default_factory=Counter)
    languages: Counter = field(default_factory=Counter)
    templates: Counter = field(default_factory=Counter)
    drops: Counter = field(default_factory=Counter)  # by reason
    empty_results: int = 0
    sql_examples: int = 0

    def text(self) -> str:
        lines = [f"Examples: {dict(self.examples)}", f"By kind: {dict(self.kinds)}",
                 f"By language: {dict(self.languages)}",
                 f"SQL examples with an empty result: {self.empty_results}/{self.sql_examples}",
                 "Dropped versions by reason:"]  # fmt: skip
        lines += [f"  {count:5d}  {reason}" for reason, count in self.drops.most_common()] or ["  none"]
        return "\n".join(lines)


@dataclass(frozen=True)
class Job:
    """One thing to ask, ready for the writer: everything the example needs is known before the call."""

    spec: Spec
    spec_id: str
    number: int
    split: str
    today: date
    names: UserNames
    rows: int | None
    prompt: str


def build(writer: QuestionWriter, users: Sequence[int], out_dir: Path, raw_dir: Path, specs_per_user: int = SPECS_PER_USER,
          keep_users: bool = False, test_questions: tuple[str, ...] = (), workers: int = WORKERS) -> Summary:  # fmt: skip
    """Three phases, so the paid calls are not held up by the database: (1) each user in turn is seeded, their SQL
    targets run and their prompts made, then the user is removed; (2) all the writer calls, `workers` at a time;
    (3) the replies are checked and the examples written in the original order, so the dataset is the same however
    many calls ran at once."""
    catalogue, seeds = load_catalogue(), load_seeds()
    summary = Summary()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    with (raw_dir / "drops.jsonl").open("w", encoding="utf-8") as drops:

        def drop(job_spec: Spec, spec_id: str, reason: str, question: str | None = None) -> None:
            summary.drops[reason.split(":")[0]] += 1
            drops.write(json.dumps({"spec": spec_id, "template": job_spec.template, "reason": reason,
                                    "question": question}) + "\n")  # fmt: skip

        jobs = _prepare(users, catalogue, seeds, specs_per_user, keep_users, drop)
        print(f"{len(jobs)} things to ask; calling the writer ({workers} at a time)", flush=True)
        replies = _call(writer, jobs, workers)
        files = {split: (out_dir / f"{split}.jsonl").open("w", encoding="utf-8") for split in ("train", "validation")}
        try:
            with (raw_dir / "generator_replies.jsonl").open("w", encoding="utf-8") as log:
                for job, reply in zip(jobs, replies, strict=True):
                    log.write(json.dumps({"spec": job.spec_id, "template": job.spec.template, "prompt": job.prompt,
                                          "reply": reply if isinstance(reply, str) else None}) + "\n")  # fmt: skip
                    if isinstance(reply, Exception):
                        drop(job.spec, job.spec_id, f"the writer failed: {reply}")
                        continue
                    try:
                        versions = read_versions(reply)
                    except UnreadableReply as exc:
                        drop(job.spec, job.spec_id, f"unreadable reply: {exc}")
                        continue
                    for version in versions:
                        found = problems(version, job.spec, catalogue, test_questions)
                        for reason in found:
                            drop(job.spec, job.spec_id, reason, version.question)
                        if not found:
                            _write(files[job.split], job, version, summary)
        finally:
            for handle in files.values():
                handle.close()
    return summary


def _prepare(users, catalogue, seeds, specs_per_user, keep_users, drop) -> list[Job]:
    """Phase 1: for each user, seed them, run every SQL target as the app would, and make the writer's prompts."""
    settings = load_settings()
    guard, rules = SqlGlotGuard(), SqlGlotQueryRules()
    jobs: list[Job] = []
    for number in users:
        user = make_user(catalogue, number)
        split = "validation" if number in VALIDATION_USERS else "train"
        with tempfile.TemporaryDirectory() as storage:
            services = build_evaluation(settings, ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                data = UserData(user, catalogue)
                rng = random.Random(f"fyp-dataset/prompts/{number}")
                for index, spec in enumerate(make_specs(data, specs_per_user, f"fyp-dataset/specs/{number}")):
                    spec_id = f"{number}-{index}"
                    try:
                        rows = _run(spec, services, user_id, names, user.today, guard, rules)
                    except (QueryRejected, UnsafeQuery, QueryFailed) as exc:
                        drop(spec, spec_id, f"the SQL target failed: {exc}")
                        continue
                    prompt = build_generator_prompt(spec, catalogue, seeds, user.today, rng)
                    jobs.append(Job(spec, spec_id, number, split, user.today, names, rows, prompt))
            finally:
                if not keep_users:
                    remove_user(services, user_id)
        print(f"user {number}: seeded, {sum(j.number == number for j in jobs)} SQL targets run, removed", flush=True)
    return jobs


def _call(writer: QuestionWriter, jobs: list[Job], workers: int) -> list:
    """Phase 2: every writer call, `workers` at a time, in the jobs' order. A call that still fails after the
    writer's own retry is kept as its error, so one bad call never stops a paid run."""
    done = 0
    lock = threading.Lock()

    def one(job: Job):
        nonlocal done
        try:
            return writer.write(job.spec, job.prompt, seed=_seed(job.spec_id))
        except Exception as exc:  # noqa: BLE001 - logged as a drop
            return exc
        finally:
            with lock:
                done += 1
                if done % 50 == 0 or done == len(jobs):
                    print(f"  {done}/{len(jobs)} replies", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, jobs))


def _write(handle, job: Job, version, summary: Summary) -> None:
    example = _example(job.spec, version, job.names, job.today, job.rows, job.number, job.split, job.spec_id)
    handle.write(json.dumps(example, ensure_ascii=False) + "\n")
    summary.examples[job.split] += 1
    summary.kinds["follow_up" if job.spec.base else job.spec.kind] += 1
    summary.languages[version.language] += 1
    summary.templates[job.spec.template] += 1
    if job.spec.kind == "sql":
        summary.sql_examples += 1
        summary.empty_results += job.rows == 0


def _run(spec: Spec, services, user_id: int, names, today, guard, rules) -> int | None:
    """Runs the target (and a follow-up's earlier SQL) as the app would; returns how many rows held a value."""
    if spec.kind != "sql":
        return None
    for sql in ((spec.base.target,) if spec.base else ()) + (spec.target,):
        rows = services.assistant.run_query(user_id, rules.prepare(guard.check(sql), names, today)).rows
    return sum(1 for row in rows if any(value not in (None, 0) for value in row))


def _example(spec: Spec, version, names, today, rows, number: int, split: str, spec_id: str) -> dict:
    history = (Exchange(clean_question(version.first), spec.base.target),) if spec.base else ()
    target = spec.target if spec.kind in ("sql", "unsupported") else version.reply
    return {
        "messages": [{"role": "user", "content": build_prompt(clean_question(version.question), names, today, history)},
                     {"role": "assistant", "content": target}],
        "labels": {"template": spec.template, "kind": "follow_up" if spec.base else spec.kind,
                   "language": version.language, "user": number, "split": split, "spec": spec_id,
                   "result_rows": rows, **{k: v for k, v in spec.labels.items() if v is not None}},
    }  # fmt: skip


def _seed(spec_id: str) -> int:
    user, index = spec_id.split("-")
    return int(user) * 1000 + int(index)


def test_questions(extra: Path | None) -> tuple[str, ...]:
    """The questions no training example may be a near-duplicate of: the pilot questions, and the user's own test
    set when given (a JSON file with a "questions" list, as the pilot's, or one question per line)."""
    found = [q["question"] for q in json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]]
    if extra:
        text = extra.read_text(encoding="utf-8")
        found += [q["question"] for q in json.loads(text)["questions"]] if extra.suffix == ".json" else [
            line.strip() for line in text.splitlines() if line.strip()]  # fmt: skip
    return tuple(found)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the fine-tuning dataset.")
    parser.add_argument("--model", default="stand-in", help='"stand-in" (default, free) or the model to call')
    parser.add_argument("--base-url", help="the OpenAI-compatible API (default: ASSISTANT_BASE_URL)")
    parser.add_argument("--users", type=int, default=USER_COUNT, help="build users 1..N (default all 30)")
    parser.add_argument("--per-user", type=int, default=SPECS_PER_USER, help="things to ask per user")
    parser.add_argument("--keep-users", action="store_true", help="leave the synthetic users in the database")
    parser.add_argument("--test-questions", type=Path, help="the user's test set, to keep near-duplicates out")
    parser.add_argument("--workers", type=int, default=WORKERS, help="writer calls at once (default 8)")
    parser.add_argument("--yes", action="store_true", help="confirm the calls to a real model")
    args = parser.parse_args(argv)

    users = range(1, args.users + 1)
    if args.model == "stand-in":
        writer, out_dir, raw_dir = StandInWriter(), RAW_DIR / "stand-in", RAW_DIR / "stand-in"
    else:
        settings = load_settings()
        base_url = args.base_url or settings.assistant_base_url
        if not args.yes:
            print(f"This run makes about {len(users) * args.per_user} calls to {args.model} at {base_url}, which may "
                  "cost money. Add --yes to start.")  # fmt: skip
            return 1
        api_key = settings.assistant_api_key
        if not api_key:
            raise SystemExit("No API key: set ASSISTANT_API_KEY")
        writer, out_dir, raw_dir = QwenWriter(base_url, api_key, args.model), DATA_DIR, RAW_DIR
    summary = build(writer, users, out_dir, raw_dir, args.per_user, args.keep_users,
                    test_questions(args.test_questions), args.workers)
    print(summary.text())
    print(f"\nExamples: {out_dir}\nGenerator replies and drops: {raw_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
