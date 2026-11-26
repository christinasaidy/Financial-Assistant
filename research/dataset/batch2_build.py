"""Free, two-stage batch-2 build: --prepare, then --replay --review PATH.

Prepare validates all 960 targets before publishing jobs.jsonl and 40-job chunks.
Writers return the existing {spec, template, prompt, reply} log format; source
references belong in separate metadata, never in the versions JSON. Replay uses
the saved snapshot, not a regenerated plan or a database connection.

Review JSON must have completed=true, a named reviewer, the criteria below, and
one entry per Arabizi/mixed version (indices 0..3). Each entry binds the complete
effective Version, including first and the users_reply replacement, and a SHA-256
of the complete Job snapshot to a keep/drop decision and reason. Old manifests
without job fingerprints require fresh review. make_review_manifest creates an INCOMPLETE starting point;
it never certifies review. Review against the spec, not just automated checks.
"""

import argparse
import hashlib
import json
import random
import tempfile
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path

from research.dataset import build
from research.dataset.batch2 import SEED_PREFIX, make_batch2_plan
from research.dataset.catalogue import load_catalogue
from research.dataset.checks import near_duplicate, problems, read_versions
from research.dataset.generator_prompt import LANGUAGES, build_generator_prompt, load_seeds, versions_schema
from research.dataset.replies import users_reply
from research.dataset.templates import Spec, UserData
from research.dataset.users import make_user, remove_user, seed_user

RAW_DIR = build.RAW_DIR / "batch2"
DATA_DIR = build.DATA_DIR / "batch2"
REVIEW_FILE = RAW_DIR / "review.json"
REVIEW_CRITERIA = (
    "Exact spec meaning: item, shop, brand, period, units and operation; no invented constraints",
    "Natural Lebanese seed style, Latin script, correct service/payment wording",
    "Follow-up first matches its base; follow-up changes only the specified constraint",
    "Effective reply matches the question and kind; drop rather than rewrite when unsure",
)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _json(text):
    return json.loads(text, object_pairs_hook=_object)


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _jsonl(values):
    return "".join(_dump(value) + "\n" for value in values)


def _fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_jobs(jobs, complete=False):
    """Reject ambiguous identity, cross-split users and incomplete full plans."""
    if not jobs:
        raise ValueError("No jobs")
    ids, prompts, counts = set(), set(), Counter()
    for job in jobs:
        if type(job.number) is not int or not 1 <= job.number <= 30:
            raise ValueError("Only synthetic users 1..30 are permitted")
        split = "train" if job.number <= 27 else "validation"
        prefix = f"b2-{job.number}-"
        index = job.spec_id.removeprefix(prefix)
        if (job.split != split or not job.spec_id.startswith(prefix) or not index.isdecimal()
                or str(int(index)) != index):
            raise ValueError("Invalid batch-2 identity or split")
        if job.spec_id in ids or job.prompt in prompts or not job.prompt.strip():
            raise ValueError("Missing or duplicate job/prompt")
        if job.spec.kind == "sql" and (type(job.rows) is not int or job.rows < 0):
            raise ValueError("SQL job has no validated row count")
        ids.add(job.spec_id)
        prompts.add(job.prompt)
        counts[job.number] += 1
    if complete:
        expected = {n: 30 if n <= 27 else 50 for n in range(1, 31)}
        if counts != expected or ids != {f"b2-{n}-{i}" for n, count in expected.items() for i in range(count)}:
            raise ValueError("Expected train 30/user and validation 50/user (960 jobs)")


def save_jobs(jobs, raw_dir, metadata, chunk_size=40, validate=None, seed=SEED_PREFIX):
    """Publish a validated snapshot. Fingerprints detect edits, not malicious forgery."""
    (validate or validate_jobs)(jobs)
    if type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    text = _jsonl(asdict(job) for job in jobs)
    manifest = {"format": 1, "jobs_sha256": _fingerprint(text), "count": len(jobs),
                "seed": seed, "metadata": metadata,
                "reproducibility": "Saved specs, prompts, names, dates and validated row counts are authoritative. "
                "Replay uses current checks/catalogue/reply rules; pin the code revision for identical output."}
    raw_dir.mkdir(parents=True, exist_ok=True)
    chunks = raw_dir / "jobs"
    chunks.mkdir(exist_ok=True)
    # Do not leave stale assignment chunks when republishing a smaller snapshot.
    for old in chunks.glob("chunk-*.jsonl"):
        old.unlink()
    (raw_dir / "jobs.jsonl").write_text(text, encoding="utf-8")
    for start in range(0, len(jobs), chunk_size):
        (chunks / f"chunk-{start // chunk_size:03d}.jsonl").write_text(
            _jsonl(asdict(job) for job in jobs[start:start + chunk_size]), encoding="utf-8")
    (raw_dir / "prepare.json").write_text(_dump(manifest) + "\n", encoding="utf-8")


def _spec(data):
    return Spec(**{**data, "mentions": tuple(tuple(group) for group in data["mentions"]),
                   "base": _spec(data["base"]) if data["base"] else None})


def load_jobs(raw_dir, validate=None):
    text = (raw_dir / "jobs.jsonl").read_text(encoding="utf-8")
    manifest = _json((raw_dir / "prepare.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or manifest.get("jobs_sha256") != _fingerprint(text):
        raise ValueError("Saved jobs fingerprint mismatch; prepare again")
    jobs = []
    for line in text.splitlines():
        entry = _json(line)
        jobs.append(build.Job(**{**entry, "spec": _spec(entry["spec"]),
                                 "today": date.fromisoformat(entry["today"]),
                                 "names": build.UserNames(**entry["names"])}))
    (validate or validate_jobs)(jobs)
    if manifest.get("count") != len(jobs):
        raise ValueError("Saved job count mismatch")
    return jobs


def prepare(raw_dir=RAW_DIR):
    """Plan globally per split, validate via the existing services, always clean up."""
    catalogue, seeds = load_catalogue(), load_seeds()
    users = {n: make_user(catalogue, n) for n in range(1, 31)}
    specs, metadata = {}, {}
    for split, numbers, count in (("train", range(1, 28), 30), ("validation", range(28, 31), 50)):
        plan = make_batch2_plan([UserData(users[n], catalogue) for n in numbers],
                                dict.fromkeys(numbers, count), f"{SEED_PREFIX}/{split}")
        specs.update(plan.specs)
        metadata[split] = {key: getattr(plan, key) for key in (
            "item_shortfalls", "feature_shortfalls", "feature_counts", "diversity_shortfalls")}
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    jobs = []
    for number, user in users.items():
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                for index, spec in enumerate(specs[number]):
                    spec_id = f"b2-{number}-{index}"
                    rows = build._run(spec, services, user_id, names, user.today, guard, rules)
                    prompt = build_generator_prompt(spec, catalogue, seeds, user.today,
                                                    random.Random(f"{SEED_PREFIX}/prompts/{number}/{index}"))
                    jobs.append(build.Job(spec, spec_id, number, "train" if number <= 27 else "validation",
                                          user.today, names, rows, prompt))
            finally:
                remove_user(services, user_id)
    validate_jobs(jobs, complete=True)
    save_jobs(jobs, raw_dir, metadata)
    return jobs


def read_reply(text, spec):
    """Enforce versions_schema AND its required positional language order."""
    if not isinstance(text, str):
        raise ValueError("Missing writer reply")
    data = _json(text)
    if not isinstance(data, dict) or set(data) != {"versions"}:
        raise ValueError("Reply must contain only versions")
    entries = data["versions"]
    fields = set(versions_schema(spec)["properties"]["versions"]["items"]["required"])
    if not isinstance(entries, list) or len(entries) != len(LANGUAGES):
        raise ValueError("Expected six versions")
    for entry, language in zip(entries, LANGUAGES, strict=True):
        if (not isinstance(entry, dict) or set(entry) != fields
                or any(not isinstance(value, str) for value in entry.values())
                or entry["language"] != language):
            raise ValueError("Version fields or language order do not match the schema")
    versions = read_versions(text)
    if tuple(v.language for v in versions) != LANGUAGES:
        raise ValueError("Parsed language order mismatch")
    return versions


def load_replies(path, jobs, validate=None):
    (validate or validate_jobs)(jobs)
    expected = {job.prompt: job for job in jobs}
    replies = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = _json(line)
        if not isinstance(entry, dict) or set(entry) != {"spec", "template", "prompt", "reply"}:
            raise ValueError("Invalid generator reply log schema")
        prompt = entry["prompt"]
        if prompt not in expected or prompt in replies:
            raise ValueError("Unknown or duplicate prompt in reply log")
        job = expected[prompt]
        if entry["spec"] != job.spec_id or entry["template"] != job.spec.template:
            raise ValueError("Reply log identity mismatch")
        replies[prompt] = read_reply(entry["reply"], job.spec)
    if set(replies) != set(expected):
        raise ValueError("Missing prompts in reply log")
    return replies


def effective_replies(jobs, replies, catalogue, seed=SEED_PREFIX):
    return {job.prompt: [users_reply(version, job.spec, catalogue,
                                   random.Random(f"{seed}/replies/{job.spec_id}/{index}"))
                        for index, version in enumerate(replies[job.prompt])] for job in jobs}


def export_assignments(raw_dir=RAW_DIR):
    """Transport saved prompts verbatim into readable 40-job writer assignments."""
    jobs = load_jobs(raw_dir)
    chunks = []
    for start in range(0, len(jobs), 40):
        parts = ["# Batch-2 writing assignment\n\n"
                 "Read every job's complete prompt and schema. Author one JSONL object per job: "
                 '`{"spec": "b2-<user>-<index>", "versions": [...]}`.\n'
                 "Language order: arabizi, arabizi, arabizi, mixed, english, english.\n"
                 "Save to authored/ with this chunk's filename and .jsonl extension. "
                 "Keep source references in separate metadata.\n"
                 "This file is transport only; the prompts below are the exact saved prompts.\n"]
        for job in jobs[start:start + 40]:
            # Choose a fence that cannot close inside the unmodified prompt.
            fence = "```"
            while fence in job.prompt:
                fence += "`"
            schema = json.dumps(versions_schema(job.spec), ensure_ascii=False, indent=2)
            parts.append(f"\n## {job.spec_id}\n\n### Exact prompt\n{fence}text\n"
                         + job.prompt + f"\n{fence}\n\n### versions_schema\n```json\n{schema}\n```\n")
        chunks.append("".join(parts))
    directory = raw_dir / "assignments"
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob("chunk-*.md"):
        old.unlink()
    paths = []
    for index, text in enumerate(chunks):
        path = directory / f"chunk-{index:03d}.md"
        path.write_text(text, encoding="utf-8", newline="")
        paths.append(path)
    return paths


def collect_authored(raw_dir=RAW_DIR, validate=None):
    """Validate manually authored versions, then attach original prompts; generate no text."""
    jobs = load_jobs(raw_dir, validate)
    expected = {job.spec_id: job for job in jobs}
    authored = {}
    for path in sorted((raw_dir / "authored").glob("chunk-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = _json(line)
            if not isinstance(entry, dict) or set(entry) != {"spec", "versions"}:
                raise ValueError("Authored entries must contain only spec and versions")
            spec_id = entry["spec"]
            if not isinstance(spec_id, str) or spec_id not in expected or spec_id in authored:
                raise ValueError("Unknown or duplicate authored spec ID")
            reply = _dump({"versions": entry["versions"]})
            read_reply(reply, expected[spec_id].spec)
            authored[spec_id] = reply
    if set(authored) != set(expected):
        raise ValueError("Missing authored spec IDs; every saved job must appear exactly once")
    text = _jsonl({"spec": job.spec_id, "template": job.spec.template, "prompt": job.prompt,
                   "reply": authored[job.spec_id]} for job in jobs)
    output = raw_dir / "generator_replies.jsonl"
    output.write_text(text, encoding="utf-8")
    return output


def make_review_manifest(jobs, replies):
    """Pass effective_replies output here so review binds the final assistant reply too."""
    fingerprints = {job.spec_id: _fingerprint(_dump(asdict(job))) for job in jobs}
    return {"completed": False, "reviewer": "", "criteria": list(REVIEW_CRITERIA), "entries": [
        {"spec": job.spec_id, "index": index, "job_sha256": fingerprints[job.spec_id],
         "version": asdict(version), "decision": "pending", "reason": ""}
        for job in jobs for index, version in enumerate(replies[job.prompt])
        if version.language in ("arabizi", "mixed")]}


def load_review(path, jobs, replies):
    review = _json(path.read_text(encoding="utf-8"))
    if (review.get("completed") is not True or not isinstance(review.get("reviewer"), str)
            or not review["reviewer"].strip() or review.get("criteria") != list(REVIEW_CRITERIA)):
        raise ValueError("Explicit completed review with reviewer and criteria is required")
    expected = {(e["spec"], e["index"]): e
                for e in make_review_manifest(jobs, replies)["entries"]}
    found = {}
    if not isinstance(review.get("entries"), list):
        raise ValueError("Missing review entries")
    for entry in review["entries"]:
        key = (entry.get("spec"), entry.get("index"))
        if (type(entry.get("index")) is not int or key not in expected or key in found
                or entry.get("version") != expected[key]["version"]
                or entry.get("job_sha256") != expected[key]["job_sha256"]
                or entry.get("decision") not in ("keep", "drop")
                or not isinstance(entry.get("reason"), str) or not entry["reason"].strip()):
            raise ValueError("Missing, duplicate, stale or undecided review entry")
        found[key] = entry
    if set(found) != set(expected):
        raise ValueError("Review must cover every Arabizi/mixed version including first")
    return found


def replay(raw_dir=RAW_DIR, out_dir=DATA_DIR, review=REVIEW_FILE, complete=False, validate=None, catalogue=None,
           seed=SEED_PREFIX):
    """`validate`, `catalogue` and `seed` default to batch 2's; batch 3 passes its own (2026-11-15)."""
    jobs = load_jobs(raw_dir, validate)
    (validate or validate_jobs)(jobs, complete=complete)
    catalogue = catalogue or load_catalogue()
    replies = effective_replies(jobs, load_replies(raw_dir / "generator_replies.jsonl", jobs, validate), catalogue,
                                seed)
    reviewed = load_review(review, jobs, replies)
    held_out = build.test_questions(None)  # internal only; never put matched evaluation text in artifacts
    accepted, drops = [], []
    summary = build.Summary()
    for job in jobs:
        for index, version in enumerate(replies[job.prompt]):
            reasons = problems(version, job.spec, catalogue, held_out)
            reasons = ["near-duplicate of a test question" if r.startswith("near-duplicate of a test question")
                       else r for r in reasons]
            if version.first and near_duplicate(version.first, held_out):
                reasons.append("earlier question near-duplicate of a test question")
            entry = reviewed.get((job.spec_id, index))
            if entry and entry["decision"] == "drop":
                reasons.append("dropped in review: " + entry["reason"])
            for reason in reasons:
                summary.drops[reason.split(":")[0]] += 1
                drops.append({"spec": job.spec_id, "template": job.spec.template, "index": index,
                              "reason": reason})
            if not reasons:
                accepted.append((job, version))
    # All validation, review and checks succeed before any output is replaced.
    out_dir.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation"):
        with (out_dir / f"{split}.jsonl").open("w", encoding="utf-8") as handle:
            for job, version in accepted:
                if job.split == split:
                    build._write(handle, job, version, summary)  # reuses _example and Summary accounting
    (raw_dir / "drops.jsonl").write_text(_jsonl(drops), encoding="utf-8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--replay", action="store_true")
    mode.add_argument("--export-assignments", action="store_true")
    mode.add_argument("--collect-authored", action="store_true")
    parser.add_argument("--review", type=Path, default=REVIEW_FILE)
    args = parser.parse_args(argv)
    if args.prepare:
        jobs = prepare()
        print(f"Validated {len(jobs)} jobs; assignments: {RAW_DIR / 'jobs'}")
        print(f"Coverage counts and shortfalls: {RAW_DIR / 'prepare.json'}")
    elif args.export_assignments:
        paths = export_assignments()
        print(f"Exported {len(paths)} assignment chunks: {RAW_DIR / 'assignments'}")
    elif args.collect_authored:
        print(f"Collected authored replies: {collect_authored()}")
    else:
        print(replay(review=args.review, complete=True).text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
