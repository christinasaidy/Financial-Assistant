"""The evaluation end to end, on the real database with stand-in models (no real model is ever called)."""

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from research.evaluation import run
from research.evaluation.expected_model import ExpectedAnswersModel, question_in
from research.evaluation.questions import load_questions
from research.evaluation.wiring import build_evaluation

TODAY, QUESTIONS = load_questions()
MONEY = "SELECT currency, SUM(line_total) AS total_spent FROM purchases WHERE {where} GROUP BY currency"


class ScriptedModel(ExpectedAnswersModel):
    """The expected answers, except for the questions given another reply (an exception is raised instead)."""

    def __init__(self, replies: dict[str, object]) -> None:
        super().__init__(QUESTIONS)
        self._replies = {next(q.question for q in QUESTIONS if q.id == key): reply for key, reply in replies.items()}

    def write_sql(self, prompt: str) -> str:
        reply = self._replies.get(question_in(prompt))
        if isinstance(reply, Exception):
            raise reply
        return reply if reply is not None else super().write_sql(prompt)


def evaluated(settings, model):
    with tempfile.TemporaryDirectory() as storage:
        evaluation = build_evaluation(settings, model, TODAY, Path(storage))
        return {report.question.id: report for report in run.evaluate(evaluation, QUESTIONS, TODAY)}


def evaluation_users(settings) -> int:
    with create_engine(settings.database_url).connect() as conn:
        return conn.execute(text("SELECT count(*) FROM users WHERE email LIKE 'evaluation-%@evaluation.local'")).scalar()


def test_the_expected_answers_score_everything_and_the_user_is_removed(settings):
    before = evaluation_users(settings)
    reports = evaluated(settings, ExpectedAnswersModel(QUESTIONS))
    assert [qid for qid, r in reports.items() if not r.score.correct] == []
    assert all(r.score.first_try for r in reports.values())
    assert evaluation_users(settings) == before


def test_the_data_catches_the_tempting_wrong_queries(settings):
    """Each of these is a plausible mistake. The data was built so that it gives a different result."""
    wrong = {
        "P01": "SELECT currency, SUM(total) AS total_spent FROM receipts GROUP BY currency",  # no date filter
        "P04": "SELECT currency, SUM(total) AS total_spent FROM receipts "
               "WHERE receipt_date >= CURRENT_DATE - INTERVAL '7 days' GROUP BY currency",  # last 7 days
        "P18": MONEY.format(where="item_name IN ('water', 'water heater')"),
        "P22": MONEY.format(where="item_name IN ('milk', 'milk powder') AND receipt_date >= '2026-10-01' "
                                  "AND receipt_date < '2026-11-01'"),
        "P23": MONEY.format(where="item_name IN ('tea', 'iced tea')"),
        "P24": MONEY.format(where="item_name = 'spaghetti'"),  # any brand
        "P32": "SELECT COUNT(*) FROM purchases WHERE item_name = 'manakish'",  # lines, not receipts
        "P37": MONEY.format(where="item_name IN ('chicken', 'chicken shawarma')"),
    }  # fmt: skip
    right_in_another_shape = {
        "P06": "SELECT currency, SUM(amount) AS spent, SUM(amount_usd) AS spent_usd FROM category_spending "
               "WHERE category = 'Groceries' AND receipt_date >= '2026-11-01' GROUP BY currency",
        "P33": "SELECT CAST(date_trunc('month', receipt_date) AS DATE) AS m, currency, SUM(amount) FROM "
               "category_spending WHERE category = 'Dining' AND receipt_date >= '2026-09-01' "
               "AND receipt_date < '2026-11-01' GROUP BY 1, 2",
    }  # fmt: skip
    refused_twice = {"P16": "SELECT SUM(line_total) FROM purchases WHERE item_name ILIKE '%laban%'"}
    reports = evaluated(settings, ScriptedModel({**wrong, **right_in_another_shape, **refused_twice}))

    assert {qid: reports[qid].score.reason for qid in wrong} == dict.fromkeys(wrong, "wrong result")
    assert all(reports[qid].score.correct for qid in right_in_another_shape)
    assert reports["P16"].score.reason.startswith("failed: Item names must match exactly")
    assert len(reports["P16"].outcome.attempts) == 2


def test_the_user_is_removed_even_if_the_run_crashes(settings):
    before = evaluation_users(settings)
    with pytest.raises(RuntimeError, match="the model crashed"):
        evaluated(settings, ScriptedModel({"P10": RuntimeError("the model crashed")}))
    assert evaluation_users(settings) == before


def test_a_real_model_needs_yes_before_any_call(capsys):
    assert run.main(["--model", "Qwen/Qwen3.8-27B"]) == 1
    assert "makes up to 94 calls" in capsys.readouterr().out


def test_every_result_records_the_code_it_measured():
    commit = run._backend_commit()
    assert len(commit["backend_commit"]) == 40 and isinstance(commit["uncommitted_changes"], bool)


def test_the_summary_lists_what_went_wrong(settings):
    reports = evaluated(settings, ScriptedModel({"P18": MONEY.format(where="item_name IN ('water', 'water heater')")}))
    text_ = run.summary(list(reports.values()), "scripted")
    assert "Correct: 46/47 (98%)" in text_
    assert "P18 [en, item] wrong result: How much did I spend on water?" in text_
    assert "Spelling groups right in every spelling: 4/4" in text_


def test_follow_ups_send_their_earlier_question_and_sql(settings):
    prompts = []

    class Recording(ExpectedAnswersModel):
        def write_sql(self, prompt: str) -> str:
            prompts.append(prompt)
            return super().write_sql(prompt)

    evaluated(settings, Recording(QUESTIONS))
    follow_up = next(p for p in prompts if p.endswith("Question: and last month?\nReply:"))
    assert "Earlier in this chat:\nQuestion: How much did I spend on groceries this month?\nReply: SELECT" in follow_up


def test_the_seed_confirms_35_receipts_and_leaves_one_waiting_for_review(settings):
    from app.domain.receipts.status import ReceiptStatus
    from research.evaluation.seed import remove_user, seed_user

    with tempfile.TemporaryDirectory() as storage:
        evaluation = build_evaluation(settings, ExpectedAnswersModel(QUESTIONS), TODAY, Path(storage))
        user_id = seed_user(evaluation)
        try:
            visible = evaluation.assistant.run_query(user_id, "SELECT COUNT(*) FROM receipts").rows[0][0]
            statuses = [receipt.status for receipt in evaluation.receipts.list_all(user_id)]
        finally:
            remove_user(evaluation, user_id)
    assert visible == 35
    assert statuses.count(ReceiptStatus.NEEDS_REVIEW) == 1 and len(statuses) == 36
