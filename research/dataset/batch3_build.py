"""Batch 3 build (approved 2026-11-15), the same stages as batch 2, on its own users and catalogue extension:

    python -m research.dataset.batch3_build --prepare          # plan, seed each user, run every SQL, save the jobs
    python -m research.dataset.batch3_build --collect-authored # check the written versions (raw/batch3/authored/)
    python -m research.dataset.batch3_build --make-review      # an INCOMPLETE review manifest to fill in
    python -m research.dataset.batch3_build --replay           # checks + review -> data/batch3/{train,validation}.jsonl

Batch 2's tools are reused with batch 3's job rules, catalogue and seed, so batch 2 itself is unchanged. Batch 4 runs
the same stages with its own `Batch` (batch4_build.py).
"""

import argparse
import json
import random
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from functools import partial
from pathlib import Path

from research.dataset import batch2_build as b2
from research.dataset import batch3, build
from research.dataset.generator_prompt import build_generator_prompt, load_seeds
from research.dataset.users import remove_user, seed_user


@dataclass(frozen=True)
class Batch:
    """What makes a batch its own: its users and their days, its id prefix, catalogue, plan and seed."""

    name: str  # "batch3": the raw/ and data/ folder, and the ids' prefix "b3"
    prefix: str
    todays: dict[int, date]
    train: tuple[int, ...]
    validation: tuple[int, ...]
    load_catalogue: Callable
    user: Callable
    plan: Callable
    seed: str

    @property
    def label(self) -> str:  # "batch-3", as the messages say
        return f"batch-{self.name.removeprefix('batch')}"

    @property
    def raw_dir(self) -> Path:
        return build.RAW_DIR / self.name

    @property
    def data_dir(self) -> Path:
        return build.DATA_DIR / self.name


BATCH3 = Batch("batch3", "b3", batch3.TODAYS, batch3.TRAIN, batch3.VALIDATION, batch3.load_batch3_catalogue,
               batch3.batch3_user, batch3.plan, batch3.SEED_PREFIX)  # fmt: skip
RAW_DIR = BATCH3.raw_dir
DATA_DIR = BATCH3.data_dir
REVIEW_FILE = RAW_DIR / "review.json"


def validate_jobs(jobs, complete=False, batch: Batch = BATCH3):
    """A batch's identity: its users only (31 is the test user), ids <prefix>-<user>-<index>, one prompt per job."""
    if not jobs:
        raise ValueError("No jobs")
    first, last = min(batch.todays), max(batch.todays)
    ids, prompts = set(), set()
    for job in jobs:
        if type(job.number) is not int or job.number not in batch.todays:
            raise ValueError(f"Only the {batch.label} users {first}..{last} are permitted")
        split = "train" if job.number in batch.train else "validation"
        prefix = f"{batch.prefix}-{job.number}-"
        index = job.spec_id.removeprefix(prefix)
        if job.split != split or not job.spec_id.startswith(prefix) or not index.isdecimal() or str(int(index)) != index:
            raise ValueError(f"Invalid {batch.label} identity or split")
        if job.spec_id in ids or job.prompt in prompts or not job.prompt.strip():
            raise ValueError("Missing or duplicate job/prompt")
        if job.today != batch.todays[job.number]:
            raise ValueError(f"A {batch.label} job must use its user's set today")
        if job.spec.kind == "sql" and (type(job.rows) is not int or job.rows < 0):
            raise ValueError("SQL job has no validated row count")
        ids.add(job.spec_id)
        prompts.add(job.prompt)


def prepare(raw_dir=None, batch: Batch = BATCH3):
    """Plan, then seed each user, run every target as the app would, and always remove the user."""
    raw_dir = raw_dir or batch.raw_dir
    catalogue, seeds = batch.load_catalogue(), load_seeds()
    specs = {**batch.plan(batch.train, catalogue=catalogue), **batch.plan(batch.validation, one_each=True,
                                                                          catalogue=catalogue)}  # fmt: skip
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    validate = partial(validate_jobs, batch=batch)
    jobs = []
    for number in batch.train + batch.validation:
        user = batch.user(number, catalogue).user
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                for index, spec in enumerate(specs[number]):
                    rows = build._run(spec, services, user_id, names, user.today, guard, rules)
                    prompt = build_generator_prompt(spec, catalogue, seeds, user.today,
                                                    random.Random(f"{batch.seed}/prompts/{number}/{index}"))
                    jobs.append(build.Job(spec, f"{batch.prefix}-{number}-{index}", number,
                                          "train" if number in batch.train else "validation", user.today, names,
                                          rows, prompt))  # fmt: skip
            finally:
                remove_user(services, user_id)
    validate(jobs)
    metadata = {"templates": dict(Counter(job.spec.template for job in jobs)),
                "kinds": dict(Counter(job.spec.kind for job in jobs))}
    b2.save_jobs(jobs, raw_dir, metadata, chunk_size=25, validate=validate, seed=batch.seed)
    return jobs


def make_review(raw_dir=None, batch: Batch = BATCH3):
    raw_dir = raw_dir or batch.raw_dir
    validate = partial(validate_jobs, batch=batch)
    jobs = b2.load_jobs(raw_dir, validate)
    replies = b2.effective_replies(jobs, b2.load_replies(raw_dir / "generator_replies.jsonl", jobs, validate),
                                   batch.load_catalogue(), batch.seed)
    manifest = b2.make_review_manifest(jobs, replies)
    path = raw_dir / "review.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path


def replay(raw_dir=None, out_dir=None, review=None, batch: Batch = BATCH3):
    raw_dir = raw_dir or batch.raw_dir
    return b2.replay(raw_dir, out_dir or batch.data_dir, review or raw_dir / "review.json",
                     validate=partial(validate_jobs, batch=batch), catalogue=batch.load_catalogue(), seed=batch.seed)


def main(argv=None, batch: Batch = BATCH3):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for flag in ("--prepare", "--collect-authored", "--make-review", "--replay"):
        mode.add_argument(flag, action="store_true")
    args = parser.parse_args(argv)
    if args.prepare:
        jobs = prepare(batch=batch)
        print(len(jobs), "jobs:", dict(Counter(job.split for job in jobs)), dict(Counter(j.spec.kind for j in jobs)))
    elif args.collect_authored:
        print("written:", b2.collect_authored(batch.raw_dir, partial(validate_jobs, batch=batch)))
    elif args.make_review:
        print("review manifest (incomplete):", make_review(batch=batch))
    else:
        print(replay(batch=batch))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
