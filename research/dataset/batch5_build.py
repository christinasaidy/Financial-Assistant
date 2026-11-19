"""Batch 5 part 1 build: the chat jobs (research/dataset/batch5.py).

    python -m research.dataset.batch5_build --prepare   # plan, seed each user, run every new SQL as the app would
    python -m research.dataset.batch5_build --replay    # the reviewed versions -> data/batch5/{train,validation}.jsonl

Like batches 3 and 4, each user is seeded through the app, every new target runs through the app's guard, answering
rules and read-only role, and the user is always removed. The jobs are saved to raw/batch5/jobs.jsonl with each new
turn's row count, for the versions to be written and reviewed.

The versions were written by the assistant and reviewed by Christina chunk by chunk (raw/batch5/authored/, 8 chunks of
20 jobs, approved 2026-11-19; review sheets raw/batch5/review_chunk*.md). Each becomes one chat example: the first
question (one of her stored, reviewed versions, with its own gold reply), the new turns before the last with their
targets, then the last new turn as the question and its target as the reply. Nothing is written unless every version
passes: 4 per job (3 Arabizi/mixed and 1 English, each on another stored version), the right number of lines, a B
answer named for each version, no rejected spelling, and no line near a test or pilot question.
"""

import argparse
import json
import re
import tempfile
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.domain.assistant.prompt import Exchange, build_prompt

from research.dataset import batch5, build
from research.dataset.checks import near_duplicate
from research.dataset.rerender import read_prompt
from research.dataset.users import gender_of, remove_user, seed_user

RAW_DIR = build.RAW_DIR / "batch5"
JOBS_FILE = RAW_DIR / "jobs.jsonl"
AUTHORED_DIR = RAW_DIR / "authored"
DATA_DIR = build.DATA_DIR / "batch5"
# Spellings Christina rejected (2026-11-19): never in a new line.
REJECTED = ("li fet", "fetou", "jem3at", "eshhor", "ekhirin", "sarle spent", "baskawit", "li mar2o")


class AuthoredError(ValueError):
    """The written versions do not match the jobs as approved."""


def _rows(result) -> int:
    return sum(1 for row in result.rows if any(value not in (None, 0) for value in row))


def prepare(jobs_file: Path = JOBS_FILE) -> list[dict]:
    jobs = batch5.plan()
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    saved = []
    for number in sorted({job.user for job in jobs}):
        user = batch5.user_data(number).user
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                for job in (j for j in jobs if j.user == number):
                    rows, option_rows = [], []
                    for turn in job.turns:
                        run = lambda sql: _rows(services.assistant.run_query(  # noqa: E731
                            user_id, rules.prepare(guard.check(sql), names, user.today)))
                        rows.append(run(turn.target) if turn.kind == "sql" else None)
                        option_rows.append({key: run(sql) for key, sql in turn.options.items()})
                    saved.append({**asdict(job), "today": user.today.isoformat(), "rows": rows,
                                  "option_rows": option_rows})
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(job, ensure_ascii=False) + "\n" for job in saved), encoding="utf-8")
    return saved


# --- replay: the reviewed versions as training examples ---


def stored_rows(data_dir: Path = build.DATA_DIR) -> dict[tuple[str, str], dict]:
    """Every batch-3/4 example by (spec, question): the first turn of a chat is one of them."""
    found = {}
    for batch in ("batch3", "batch4"):
        for split in ("train", "validation"):
            for line in (data_dir / batch / f"{split}.jsonl").read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                found[(row["labels"]["spec"], read_prompt(row["messages"][0]["content"]).question)] = row
    return found


def load_authored(authored_dir: Path = AUTHORED_DIR) -> dict[str, list[dict]]:
    found = {}
    for chunk in sorted(authored_dir.glob("chunk-*.json")):
        for job_id, versions in json.loads(chunk.read_text(encoding="utf-8")).items():
            if job_id in found:
                raise AuthoredError(f"{job_id} is written twice")
            found[job_id] = versions
    return found


def check_versions(job: dict, versions: list[dict]) -> None:
    """The versions of a job as approved: 4, on different stored versions (3 Arabizi/mixed, 1 English), one line per
    new turn, a B answer named for each, no rejected spelling."""
    firsts = [v["first"] for v in versions]
    languages = [job["first_versions"][i][0] for i in firsts]
    if len(versions) != 4 or len(set(firsts)) != 4 or languages.count("english") != 1:
        raise AuthoredError(f"{job['job_id']}: needs 4 versions on 4 stored versions, exactly one of them English")
    for version in versions:
        if len(version["lines"]) != len(job["turns"]):
            raise AuthoredError(f"{job['job_id']}: {len(version['lines'])} lines for {len(job['turns'])} new turns")
        options = job["turns"][-1]["options"]
        if bool(options) != ("target" in version) or (options and version["target"] not in options):
            raise AuthoredError(f"{job['job_id']}: a clarified question's answer must name one of its options")
        for line in version["lines"]:
            bad = [word for word in REJECTED if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", line, re.IGNORECASE)]
            if bad:
                raise AuthoredError(f"{job['job_id']}: rejected spelling {bad} in {line!r}")


def chat_example(job: dict, version: dict, stored: dict) -> dict:
    """One version as a training example in the app's own prompt."""
    language, first_question = job["first_versions"][version["first"]]
    first = stored[(job["first_spec"], first_question)]
    parts = read_prompt(first["messages"][0]["content"])
    english = language == "english"
    history = [Exchange(first_question, first["messages"][1]["content"])]
    for turn, line in zip(job["turns"][:-1], version["lines"][:-1]):
        history.append(Exchange(line, turn["target"]))
    last = job["turns"][-1]
    if version.get("target"):
        reply = last["options"][version["target"]]
    elif last["kind"] == "reply" and english:
        reply = last["english_target"]
    else:
        reply = last["target"]
    prompt = build_prompt(version["lines"][-1], parts.names, date.fromisoformat(job["today"]), tuple(history),
                          gender=gender_of(job["user"]))  # fmt: skip
    rows = (job["option_rows"][-1].get(version["target"]) if version.get("target") else job["rows"][-1])
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}],
            "labels": {"template": f"P1{job['kind']}", "kind": "reply" if reply.startswith("REPLY:") else "sql",
                       "language": language, "user": job["user"], "split": job["split"], "spec": job["job_id"],
                       "result_rows": rows, "chat": job["sub"], "history": len(history),
                       "history_role": job["role"], "first_spec": job["first_spec"],
                       **{k: v for k, v in last["labels"].items() if isinstance(v, str)}}}  # fmt: skip


def replay(jobs_file: Path = JOBS_FILE, authored_dir: Path = AUTHORED_DIR, out_dir: Path = DATA_DIR,
           held_out: tuple[str, ...] | None = None, data_dir: Path = build.DATA_DIR) -> dict:  # fmt: skip
    """Every reviewed version as an example. Refuses (AuthoredError) before writing anything if a job is missing,
    unplanned or wrongly written; a line near a test or pilot question drops that version (counted, never shown)."""
    jobs = {job["job_id"]: job for job in map(json.loads, jobs_file.read_text(encoding="utf-8").splitlines())}
    authored = load_authored(authored_dir)
    if set(authored) != set(jobs):
        raise AuthoredError(f"written {len(authored)} jobs, planned {len(jobs)}: "
                            f"missing {sorted(set(jobs) - set(authored))[:5]}, unplanned {sorted(set(authored) - set(jobs))[:5]}")  # noqa: E501
    held_out = build.test_questions(None) if held_out is None else held_out
    stored = stored_rows(data_dir)
    out = {"train": [], "validation": []}
    near = 0
    for job_id in sorted(jobs, key=lambda j: (jobs[j]["user"], int(j.rsplit("-", 1)[1]))):
        job, versions = jobs[job_id], authored[job_id]
        check_versions(job, versions)
        for version in versions:
            if any(near_duplicate(line, held_out) for line in version["lines"]):
                near += 1
                continue
            out[job["split"]].append(chat_example(job, version, stored))
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in out.items():
        (out_dir / f"{split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                encoding="utf-8")  # fmt: skip
    return {"train": len(out["train"]), "validation": len(out["validation"]), "near test questions, dropped": near,
            "kinds": dict(Counter(r["labels"]["template"] for rows in out.values() for r in rows))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare:
        saved = prepare()
        empty = sum(1 for job in saved if job["rows"][-1] == 0)
        print(len(saved), "jobs:", dict(Counter((j["split"], j["kind"]) for j in saved)), f"| last answer empty: {empty}")
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
