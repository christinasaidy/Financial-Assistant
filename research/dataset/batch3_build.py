"""Batch 3 build (approved 2026-11-15), the same stages as batch 2, on its own users and catalogue extension:

    python -m research.dataset.batch3_build --prepare          # plan, seed each user, run every SQL, save the jobs
    python -m research.dataset.batch3_build --collect-authored # check the written versions (raw/batch3/authored/)
    python -m research.dataset.batch3_build --make-review      # an INCOMPLETE review manifest to fill in
    python -m research.dataset.batch3_build --replay           # checks + review -> data/batch3/{train,validation}.jsonl

Batch 2's tools are reused with batch 3's job rules, catalogue and seed, so batch 2 itself is unchanged.
"""

import argparse
import json
import random
import tempfile
from collections import Counter
from pathlib import Path

from research.dataset import batch2_build as b2
from research.dataset import build
from research.dataset.batch3 import SEED_PREFIX, TODAYS, TRAIN, VALIDATION, batch3_user, load_batch3_catalogue, plan
from research.dataset.generator_prompt import build_generator_prompt, load_seeds
from research.dataset.users import remove_user, seed_user

RAW_DIR = build.RAW_DIR / "batch3"
DATA_DIR = build.DATA_DIR / "batch3"
REVIEW_FILE = RAW_DIR / "review.json"


def validate_jobs(jobs, complete=False):
    """Batch-3 identity: users 32-41 only (31 is the test user), ids b3-<user>-<index>, one prompt per job."""
    if not jobs:
        raise ValueError("No jobs")
    ids, prompts = set(), set()
    for job in jobs:
        if type(job.number) is not int or job.number not in TODAYS:
            raise ValueError("Only the batch-3 users 32..41 are permitted")
        split = "train" if job.number in TRAIN else "validation"
        prefix = f"b3-{job.number}-"
        index = job.spec_id.removeprefix(prefix)
        if job.split != split or not job.spec_id.startswith(prefix) or not index.isdecimal() or str(int(index)) != index:
            raise ValueError("Invalid batch-3 identity or split")
        if job.spec_id in ids or job.prompt in prompts or not job.prompt.strip():
            raise ValueError("Missing or duplicate job/prompt")
        if job.today != TODAYS[job.number]:
            raise ValueError("A batch-3 job must use its user's set today")
        if job.spec.kind == "sql" and (type(job.rows) is not int or job.rows < 0):
            raise ValueError("SQL job has no validated row count")
        ids.add(job.spec_id)
        prompts.add(job.prompt)


def prepare(raw_dir=RAW_DIR):
    """Plan, then seed each user, run every target as the app would, and always remove the user."""
    catalogue, seeds = load_batch3_catalogue(), load_seeds()
    specs = {**plan(TRAIN, catalogue=catalogue), **plan(VALIDATION, one_each=True, catalogue=catalogue)}
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    jobs = []
    for number in TRAIN + VALIDATION:
        user = batch3_user(number, catalogue).user
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                for index, spec in enumerate(specs[number]):
                    rows = build._run(spec, services, user_id, names, user.today, guard, rules)
                    prompt = build_generator_prompt(spec, catalogue, seeds, user.today,
                                                    random.Random(f"{SEED_PREFIX}/prompts/{number}/{index}"))
                    jobs.append(build.Job(spec, f"b3-{number}-{index}", number,
                                          "train" if number in TRAIN else "validation", user.today, names, rows,
                                          prompt))  # fmt: skip
            finally:
                remove_user(services, user_id)
    validate_jobs(jobs)
    metadata = {"templates": dict(Counter(job.spec.template for job in jobs)),
                "kinds": dict(Counter(job.spec.kind for job in jobs))}
    b2.save_jobs(jobs, raw_dir, metadata, chunk_size=25, validate=validate_jobs, seed=SEED_PREFIX)
    return jobs


def make_review(raw_dir=RAW_DIR):
    jobs = b2.load_jobs(raw_dir, validate_jobs)
    replies = b2.effective_replies(jobs, b2.load_replies(raw_dir / "generator_replies.jsonl", jobs, validate_jobs),
                                   load_batch3_catalogue(), SEED_PREFIX)
    manifest = b2.make_review_manifest(jobs, replies)
    path = raw_dir / "review.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path


def replay(raw_dir=RAW_DIR, out_dir=DATA_DIR, review=REVIEW_FILE):
    return b2.replay(raw_dir, out_dir, review, validate=validate_jobs, catalogue=load_batch3_catalogue(),
                     seed=SEED_PREFIX)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for flag in ("--prepare", "--collect-authored", "--make-review", "--replay"):
        mode.add_argument(flag, action="store_true")
    args = parser.parse_args(argv)
    if args.prepare:
        jobs = prepare()
        print(len(jobs), "jobs:", dict(Counter(job.split for job in jobs)), dict(Counter(j.spec.kind for j in jobs)))
    elif args.collect_authored:
        print("written:", b2.collect_authored(RAW_DIR, validate_jobs))
    elif args.make_review:
        print("review manifest (incomplete):", make_review())
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
