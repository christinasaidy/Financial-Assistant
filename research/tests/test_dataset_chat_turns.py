"""Batch 5: chat turns the audit found missing (chat_turns.py), decided with Christina on 2026-11-23. Do not change an
expected value to make a test pass. These tests read the saved jobs."""

import json
import re

from app.domain.assistant.prompt import UserNames
from app.domain.assistant.prompt import Exchange
from research.dataset import chat_turns as c
from research.dataset.fixes import history_problem
from research.dataset.rerender import read_prompt

JOBS = [json.loads(line) for line in c.JOBS_FILE.read_text(encoding="utf-8").splitlines()]


def _rows(tmp_path):
    report = c.replay(out_dir=tmp_path)
    rows = [json.loads(x) for split in ("train", "validation")
            for x in (tmp_path / f"chat_turns_{split}.jsonl").read_text(encoding="utf-8").splitlines()]  # fmt: skip
    return report, rows


def test_the_saved_jobs_give_these_chats(tmp_path):
    report, _ = _rows(tmp_path)
    assert report == {"train": {"CH1": 120, "CH4": 80, "CH3": 17}, "validation": {"CH1": 12, "CH4": 8},
                      "empty, left out": ["ch3-t-3", "ch3-t-13", "ch3-t-17"], "earlier wrong": 22}  # fmt: skip


def test_a_question_about_all_spending_never_keeps_the_earlier_filter(tmp_path):
    _, rows = _rows(tmp_path)
    for row in (r for r in rows if r["labels"]["template"] == "CH1"):
        parts = read_prompt(row["messages"][0]["content"])
        assert c.FILTER.search(parts.history[0].reply) and not c.FILTER.search(row["messages"][1]["content"])
        assert history_problem(parts.history, parts.names) is None
        assert "keeps only the earlier period" in row["messages"][0]["content"]


def test_a_wrong_earlier_turn_asks_about_another_of_the_users_items():
    for job in (j for j in JOBS if j["template"] == "CH1" and j["earlier_wrong"]):
        item = re.search(r"item_name = '((?:[^']|'')*)'", job["history"][0][1]).group(1).replace("''", "'")
        assert item in job["names"]["items"]


def test_the_refused_follow_ups_are_her_forms_and_all_are_used():
    refused = [j for j in JOBS if j["template"] == "CH4"]
    assert all(j["reply"] == "UNSUPPORTED" and j["question"] in c.REFUSED for j in refused)
    assert {j["question"] for j in refused} == set(c.REFUSED)
    assert all(j["history"][0][1].startswith("SELECT") for j in refused)


def test_after_a_correction_only_the_item_or_the_month_changes():
    for job in (j for j in JOBS if j["template"] == "CH3"):
        corrected = job["history"][-1][1]
        if job["question"] == "w el shaher li mara2?":
            assert job["reply"] == corrected.replace(c.THIS_MONTH, c.LAST_MONTH) and job["reply"] != corrected
        else:
            assert re.sub(r"item_name = '[^']*'", "X", job["reply"]) == re.sub(r"item_name = '[^']*'", "X", corrected)
            assert re.fullmatch(r"w el \S+( \S+)*\?", job["question"]) and job["reply"] != corrected


def test_an_impossible_earlier_turn_is_never_planned():
    names = UserNames(items=["bread"], vendors=["Spinneys"], categories=["Dining"])
    assert history_problem((Exchange("rent?", "SELECT 1 WHERE category = 'Rent'"),), names) is not None
    for job in (j for j in JOBS if j["template"] == "CH1"):
        assert history_problem(tuple(Exchange(q, r) for q, r in job["history"]), UserNames(**job["names"])) is None


def test_a_pair_whose_earlier_turn_names_what_the_user_does_not_have_is_skipped(monkeypatch):
    names = {"items": ["bread"], "vendors": ["Spinneys"], "categories": ["Dining"]}
    base = {"names": names, "today": "2026-05-03", "user": 1, "language": "arabizi", "spec": "x"}
    rent = {**base, "question": "aday dafa3et ajar?", "sql": "SELECT 1 FROM category_spending WHERE category = 'Rent'",
            "template": "T3"}
    total = {**base, "question": "aday sarafet hal shaher?", "template": "T1",
             "sql": "SELECT SUM(total) FROM receipts WHERE receipt_date >= date_trunc('month', CURRENT_DATE)"}
    monkeypatch.setattr(c, "_stored", lambda split: [rent, total])
    monkeypatch.setattr(c, "_after_corrections", lambda: [])
    assert not [j for j in c.plan() if j["template"] == "CH1"]
    monkeypatch.setattr(c, "_stored", lambda split: [{**rent, "sql": "SELECT 1 FROM category_spending WHERE category = 'Dining'"}, total])
    assert [j for j in c.plan() if j["template"] == "CH1"]
