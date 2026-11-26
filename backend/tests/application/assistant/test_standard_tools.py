"""The Standard tools' own checks, before anything runs: unknown tools, extra fields (a model-written user_id among
them), wrong types and bad values are refused without touching a service or the database (AC-06, AC-07). What the
tools return from real data is tested against PostgreSQL in tests/integration/test_standard_mode_flow.py."""

import json
from datetime import date

import pytest

from app.application.assistant.dtos import ToolCall
from app.application.assistant.standard_tools import SPECS, StandardTools, ToolContext


class Untouchable:
    """Fails the test if a tool reaches any service or the database."""

    def __getattr__(self, name):
        raise AssertionError(f"{name} was used, but the call should have been refused first")

    def __call__(self, *args, **kwargs):
        raise AssertionError("the database was opened, but the call should have been refused first")


@pytest.fixture
def tools():
    nothing = Untouchable()
    return StandardTools(nothing, nothing, nothing, nothing, nothing, nothing, nothing)


CONTEXT = ToolContext(date(2026, 11, 23), "how much?")


def budget(**changes):
    return {"category": "Groceries", "currency": "USD", "limit_amount": "150", "year": 2026, "month": 11} | changes


def run(tools, name, args):
    outcome = tools.run(1, ToolCall("toolu_1", name, args), CONTEXT)
    return outcome, json.loads(outcome.content)


@pytest.mark.parametrize(
    ("name", "args", "problem"),
    [
        ("drop_everything", {}, "There is no tool called 'drop_everything'"),
        ("get_receipt", {"receipt_id": 5, "user_id": 2}, "Unknown input field(s): user_id"),
        ("query_receipts", {"sql": "SELECT 1", "user_id": 2}, "Unknown input field(s): user_id"),
        ("get_receipt", {}, "Missing input field(s): receipt_id"),
        ("get_receipt", {"receipt_id": "5"}, "receipt_id must be a whole number"),
        ("get_receipt", {"receipt_id": True}, "receipt_id must be a whole number"),
        ("get_receipt", {"receipt_id": 0}, "receipt_id must be a positive number"),
        ("find_names", {"kind": "person", "name": "Bob"}, "kind must be one of: vendor, item, category"),
        ("find_names", {"kind": "vendor", "name": " "}, "The name must be 1 to 200 characters"),
        ("get_budgets", {"year": 2026, "month": 13}, "month must be 1 to 12"),
        ("get_spending_summary", {"year": 1999, "month": 1, "currency": "USD"}, "year must be between 2000 and 2100"),
        ("get_spending_summary", {"year": 2026, "month": 1, "currency": "EUR"}, "currency must be one of: USD, LBP"),
        ("query_receipts", {"sql": "x" * 4001}, "The SQL must be 1 to 4000 characters"),
        ("query_receipts", "SELECT 1", "The input must be an object"),
        # Budgets: never an earlier month (they are changed on the Budgets screen), only a plain positive amount.
        ("propose_budget", budget(month=10), "A budget set here starts this month or later; earlier months are "
                                             "changed on the Budgets screen"),
        ("propose_budget", budget(year=2025, month=12), "A budget set here starts this month or later; earlier "
                                                        "months are changed on the Budgets screen"),
        ("propose_budget", budget(limit_amount="1,500"), "limit_amount must be digits only (e.g. 150 or 2500000), "
                                                         "with at most 2 decimals"),
        ("propose_budget", budget(limit_amount="-5"), "limit_amount must be digits only (e.g. 150 or 2500000), "
                                                      "with at most 2 decimals"),
        ("propose_budget", budget(limit_amount="150 alf"), "limit_amount must be digits only (e.g. 150 or "
                                                           "2500000), with at most 2 decimals"),
        ("propose_budget", budget(limit_amount="0"), "The budget amount must be greater than zero"),
        ("propose_budget", budget(currency="EUR"), "currency must be one of: USD, LBP"),
        ("propose_budget", budget(user_id=2), "Unknown input field(s): user_id"),
        # Nothing was proposed in the previous answer: refused before anything is read or set.
        ("confirm_budget", budget(), "Your previous answer did not ask the user to confirm a budget change. Propose "
                                     "it with propose_budget and ask them first"),
    ],
)
def test_bad_calls_are_refused_before_anything_runs(tools, name, args, problem):
    outcome, body = run(tools, name, args)
    assert outcome.is_error
    assert body == {"error": problem}
    assert outcome.record["ok"] is False and outcome.record["problem"] == problem


def test_no_tool_lets_the_model_choose_the_user():
    for spec in SPECS:
        assert spec.input_schema["additionalProperties"] is False
        assert not any("user" in name for name in spec.input_schema["properties"])
        assert set(spec.input_schema["required"]) == set(spec.input_schema["properties"])  # strict tool use


def test_the_tool_definitions_are_fixed_and_in_a_fixed_order():
    """They are part of the cached prefix: the same bytes for every request."""
    assert [spec.name for spec in SPECS] == ["query_receipts", "find_names", "get_receipt", "get_spending_summary",
                                             "get_budgets", "propose_budget", "confirm_budget", "save_memory",
                                             "update_memory", "forget_memory", "search_memories"]  # fmt: skip
    assert StandardTools.specs is SPECS
