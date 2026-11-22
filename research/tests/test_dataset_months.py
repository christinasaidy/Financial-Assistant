"""Batch 5: named months that already passed this year (months.py), decided with Christina on 2026-11-22: approved
questions about one month and nothing else, asked again by users whose today makes that month just passed. Do not
change an expected value to make a test pass. These tests read the stored data and the saved jobs."""

import json
import re
from datetime import date

from research.dataset import months
from research.dataset.rerender import read_prompt

JOBS = [json.loads(line) for line in months.JOBS_FILE.read_text(encoding="utf-8").splitlines()]
SOURCES = {c["question"]: c for c in months.candidates()}


def _month_and_year(sql: str) -> tuple[int, int]:
    year, month, _, _ = months._ONE_MONTH.search(sql).groups()
    return int(month), int(year)


def test_the_saved_jobs_are_the_plan_and_every_answer_has_receipts(tmp_path):
    assert months.replay(out_dir=tmp_path) == {"train": 56, "validation": 0, "empty, left out": 0,
                                               "back": {1: 40, 2: 12, 3: 4}}  # fmt: skip


def test_each_month_is_the_one_just_passed_this_year_for_its_new_user():
    for job in JOBS:
        today = date.fromisoformat(job["today"])
        month, year = _month_and_year(job["target"])
        assert year == today.year and (today.month - month) == job["back"], job["job_id"]


def test_the_question_is_unchanged_and_only_the_year_differs_from_its_source():
    for job in JOBS:
        source = SOURCES[job["question"]]
        assert months._ONE_MONTH.sub("X", job["target"]) == months._ONE_MONTH.sub("X", source["sql"])
        assert _month_and_year(job["target"])[0] == source["month"]


def test_no_question_names_a_shop_or_item_or_uses_a_rejected_spelling():
    for job in JOBS:
        assert not re.search(r"\bvendor\b|item_name|brand", job["target"])
        assert not re.search(r"\b(sarfet|baskawit|man2ish|jem3at)\b", job["question"], re.IGNORECASE)


def test_a_category_question_goes_only_to_a_user_who_has_that_category():
    for job in JOBS:
        found = re.search(r"category = '((?:[^']|'')*)'", job["target"])
        if found:
            assert found.group(1).replace("''", "'") in job["names"]["categories"]


def test_an_empty_answer_is_left_out(tmp_path):
    jobs = [dict(job, rows=0) if i == 0 else job for i, job in enumerate(JOBS)]
    saved = tmp_path / "jobs.jsonl"
    saved.write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in jobs), encoding="utf-8")
    report = months.replay(jobs_file=saved, out_dir=tmp_path / "out")
    assert report["empty, left out"] == 1 and report["train"] == 55


def test_the_example_uses_the_new_users_day(tmp_path):
    months.replay(out_dir=tmp_path)
    row = json.loads((tmp_path / "months_train.jsonl").read_text(encoding="utf-8").splitlines()[0])
    job = next(j for j in JOBS if j["job_id"] == row["labels"]["spec"])
    parts = read_prompt(row["messages"][0]["content"])
    assert parts.today == date.fromisoformat(job["today"]) and parts.question == job["question"]
