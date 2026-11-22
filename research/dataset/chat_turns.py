"""Batch 5: chat turns the audit found missing (decided with Christina on 2026-11-23; PROGRESS.md).

    python -m research.dataset.chat_turns --prepare   # seed the users of the new queries, run them as the app would
    python -m research.dataset.chat_turns --replay    # -> data/batch5/chat_turns_{split}.jsonl

All from her approved lines (batches 2-4, the corrections of part 1), put together by code:
- CH1, a question about ALL spending after a turn with an item, shop or category: her ruling, it keeps only its own
  period, never the earlier filter (fine-tune 4 kept "laban" in "3a shu sarafet hal shaher?"); in about a quarter of
  them the earlier query is a wrong one (another of the user's items), as the app's own history can be, and the new
  question still ignores it;
- CH3, a correction and then one more turn: "w el <another item>?" after an item correction (the item word from the
  catalogue's approved spellings), "w el shaher li mara2?" after a correction of this month's total;
- CH4, a short follow-up the receipts cannot answer: another person (w marti?, w zawje?, ...), the future, income or a
  budget (her approved forms) -> UNSUPPORTED.
Every query of CH3 (new SQL) runs through the app on the seeded user (removed after); CH1's are the stored gold.
"""

import argparse
import json
import random
import re
import tempfile
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.domain.assistant.prompt import Exchange, UserNames, build_prompt

from research.dataset import build
from research.dataset import templates as t
from research.dataset.fixes import history_problem
from research.dataset.rerender import UnreadablePrompt, read_prompt
from research.dataset.users import gender_of, remove_user, seed_user
from research.dataset.words import _rows, users

RAW_DIR = build.RAW_DIR / "batch5" / "chat_turns"
JOBS_FILE = RAW_DIR / "jobs.jsonl"
DATA_DIR = build.DATA_DIR / "batch5"
SEED = "fyp-dataset/batch5-chat-turns"
SOURCES = ("batch3", "batch4", "batch2")
WHOLE = ("T1", "T2", "T4", "T5", "T7", "T16", "B14", "B2")  # all spending: totals, by category, top shop, counts, summary
FILTER = re.compile(r"item_name\s*(=|IN)|vendor\s*(=|IN)|category\s*(=|IN)|brand\s*=")
WANT = {"train": {"CH1": 120, "CH4": 80}, "validation": {"CH1": 12, "CH4": 8}}
WRONG_SHARE = 0.25
REFUSED = ("w marti?", "w zawje?", "w ekhte?", "w khayye?", "w ahle?", "w rfi2e?", "w el shaher el jeye?", "w bokra?",
           "w ma3ashe?", "w el retib?", "w el budget?")  # her approved forms, 2026-11-23  # fmt: skip
THIS_MONTH = ("receipt_date >= date_trunc('month', CURRENT_DATE) AND receipt_date < date_trunc('month', CURRENT_DATE) "
              "+ INTERVAL '1 month'")  # fmt: skip
LAST_MONTH = ("receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' AND receipt_date < "
              "date_trunc('month', CURRENT_DATE)")  # fmt: skip


def _stored(split: str) -> list[dict]:
    """Her approved Arabizi / mixed SQL questions with no history: question, gold, names, today, user, template."""
    found = []
    for source in SOURCES:
        for line in (build.DATA_DIR / source / f"{split}.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            labels = row["labels"]
            if labels["kind"] != "sql" or labels["language"] == "english":
                continue
            try:
                parts = read_prompt(row["messages"][0]["content"])
            except UnreadablePrompt:
                continue
            if parts.history:
                continue
            found.append({"question": parts.question, "sql": row["messages"][1]["content"], "names": asdict(parts.names),
                          "today": parts.today.isoformat(), "user": labels["user"], "template": labels["template"],
                          "language": labels["language"], "spec": labels.get("spec")})  # fmt: skip
    return found


def _filtered(entry: dict) -> bool:
    return bool(FILTER.search(entry["sql"]))


def _whole(entry: dict) -> bool:
    sql = entry["sql"]
    return entry["template"] in WHOLE and not FILTER.search(sql) and ("receipt_date" in sql or "CURRENT_DATE" in sql)


def _wrong(sql: str, names: dict, rng: random.Random) -> str | None:
    """The earlier query about another of the user's items (a plausible mistake), or None."""
    found = re.search(r"item_name = '((?:[^']|'')*)'", sql)
    others = [i for i in names["items"] if found and i != found.group(1).replace("''", "'")]
    return sql.replace(found.group(0), f"item_name = {t.quoted(rng.choice(others))}") if others else None


def _catalogue_words() -> dict[str, str]:
    words = {}
    for name in ("catalogue.json", "catalogue_batch3.json", "catalogue_batch4.json"):
        for item in json.loads((build.DATA_DIR / name).read_text(encoding="utf-8"))["items"]:
            if item.get("words"):
                words.setdefault(item["name"], item["words"][0])
    return words


def plan() -> list[dict]:
    jobs = []
    for split in ("train", "validation"):
        rng = random.Random(f"{SEED}/{split}")
        entries = _stored(split)
        by_user = {}
        for e in entries:
            by_user.setdefault(e["user"], []).append(e)
        pairs, refusals = [], []
        for user in sorted(by_user):
            mine = by_user[user]
            whole, filtered = [e for e in mine if _whole(e)], [e for e in mine if _filtered(e)]
            for w in whole:
                for f in rng.sample(filtered, min(3, len(filtered))):
                    pairs.append((f, w))
            for e in mine:
                refusals.append(e)
        rng.shuffle(pairs)
        rng.shuffle(refusals)
        made = 0
        for f, w in pairs:
            if made >= WANT[split]["CH1"]:
                break
            earlier = f["sql"]
            wrong = rng.random() < WRONG_SHARE and _wrong(earlier, w["names"], rng)
            earlier = wrong or earlier
            names = UserNames(**w["names"])
            if history_problem((Exchange(f["question"], earlier),), names) is not None:
                continue
            jobs.append({"job_id": f"ch1-{split[0]}-{made}", "template": "CH1", "split": split, "user": w["user"],
                         "language": w["language"], "today": w["today"], "names": w["names"],
                         "history": [[f["question"], earlier]], "question": w["question"], "reply": w["sql"],
                         "earlier_wrong": bool(wrong), "from": [f["spec"], w["spec"]], "run": False})  # fmt: skip
            made += 1
        for index, e in enumerate(refusals[: WANT[split]["CH4"]]):
            jobs.append({"job_id": f"ch4-{split[0]}-{index}", "template": "CH4", "split": split, "user": e["user"],
                         "language": "arabizi", "today": e["today"], "names": e["names"],
                         "history": [[e["question"], e["sql"]]], "question": REFUSED[index % len(REFUSED)],
                         "reply": "UNSUPPORTED", "from": [e["spec"]], "run": False})  # fmt: skip
    jobs += _after_corrections()
    return jobs


def _after_corrections() -> list[dict]:
    words, jobs = _catalogue_words(), []
    for line in (DATA_DIR / "corrections_train.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        parts = read_prompt(row["messages"][0]["content"])
        corrected = row["messages"][1]["content"]
        history = [[e.question, e.reply] for e in parts.history] + [[parts.question, corrected]]
        base = {"template": "CH3", "split": "train", "user": row["labels"]["user"], "language": row["labels"]["language"],
                "today": parts.today.isoformat(), "names": asdict(parts.names), "history": history,
                "from": [row["labels"]["spec"]], "run": True}  # fmt: skip
        if row["labels"].get("correction") == "item":
            found = re.search(r"item_name = '((?:[^']|'')*)'", corrected)
            others = [i for i in parts.names.items if found and i != found.group(1) and i in words][:3]
            for other in others:
                jobs.append({**base, "job_id": f"ch3-t-{len(jobs)}", "question": f"w el {words[other]}?",
                             "reply": corrected.replace(found.group(0), f"item_name = {t.quoted(other)}")})
        elif THIS_MONTH in corrected:
            jobs.append({**base, "job_id": f"ch3-t-{len(jobs)}", "question": "w el shaher li mara2?",
                         "reply": corrected.replace(THIS_MONTH, LAST_MONTH)})
    return jobs


def prepare(jobs_file: Path = JOBS_FILE) -> list[dict]:
    jobs = plan()
    settings = build.load_settings()
    if not settings.readonly_database_url:
        raise ValueError("Prepare requires the configured read-only database role")
    guard, rules = build.SqlGlotGuard(), build.SqlGlotQueryRules()
    data = {n: d for n, _, d in users()}
    for number in sorted({j["user"] for j in jobs if j["run"]}):
        user = data[number].user
        with tempfile.TemporaryDirectory() as storage:
            services = build.build_evaluation(settings, build.ExpectedAnswersModel([]), user.today, Path(storage))
            user_id = seed_user(services, user)
            try:
                names = services.assistant.prompt_names(user_id)
                for job in (j for j in jobs if j["run"] and j["user"] == number):
                    job["rows"] = _rows(services.assistant.run_query(user_id, rules.prepare(
                        guard.check(job["reply"]), names, user.today)))  # fmt: skip
            finally:
                remove_user(services, user_id)
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs), encoding="utf-8")
    return jobs


def replay(jobs_file: Path = JOBS_FILE, out_dir: Path = DATA_DIR) -> dict:
    jobs = [json.loads(line) for line in jobs_file.read_text(encoding="utf-8").splitlines()]
    keep = ("job_id", "user", "question", "reply", "history")
    if [{k: j[k] for k in keep} for j in jobs] != [{k: j[k] for k in keep} for j in json.loads(json.dumps(plan()))]:
        raise ValueError("the saved jobs are not the plan: prepare again")
    out, empty = {"train": [], "validation": []}, []
    for job in jobs:
        if job["run"] and not job.get("rows"):
            empty.append(job["job_id"])  # nothing bought: left out, as decided for every part
            continue
        history = tuple(Exchange(q, r) for q, r in job["history"])
        prompt = build_prompt(job["question"], UserNames(**job["names"]), date.fromisoformat(job["today"]), history,
                              gender=gender_of(job["user"]))  # fmt: skip
        kind = "unsupported" if job["reply"] == "UNSUPPORTED" else "sql"
        labels = {"template": job["template"], "kind": kind, "language": job["language"], "user": job["user"],
                  "split": job["split"], "spec": job["job_id"], "part": "chat_turns", "history": len(history),
                  "history_role": "independent" if job["template"] == "CH1" else "dependent", "from": job["from"],
                  "earlier_wrong": job.get("earlier_wrong", False)}  # fmt: skip
        out[job["split"]].append({"messages": [{"role": "user", "content": prompt},
                                               {"role": "assistant", "content": job["reply"]}], "labels": labels})
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in out.items():
        (out_dir / f"chat_turns_{split}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    from collections import Counter  # noqa: PLC0415

    return {split: dict(Counter(r["labels"]["template"] for r in rows)) for split, rows in out.items()} | {
        "empty, left out": empty, "earlier wrong": sum(r["labels"]["earlier_wrong"] for r in out["train"])}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare:
        saved = prepare()
        print(len(saved), "jobs; CH3 rows:", {j["job_id"]: j.get("rows") for j in saved if j["run"]})
    else:
        print(replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
