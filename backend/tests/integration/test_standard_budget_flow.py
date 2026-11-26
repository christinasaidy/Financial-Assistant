"""Setting budgets from a Standard chat against the real database (2026-11-25): always confirmed first (the owner's
decision). propose_budget sets nothing; confirm_budget sets only what the previous answer in the same conversation
asked the user to confirm, with exactly those values, once; never an earlier month; no tool removes a budget.

Only the model is scripted, so these prove the rules, never what Sonnet would answer.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.infrastructure.config import Settings
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeAssistantModel, FakeReceiptExtractor, ScriptedChatModel, calls, says
from tests.integration.conftest import forget_usage_by_email

TODAY = date(2026, 11, 23)
ASK = "Should I set your Groceries budget to $150 a month from November 2026?"


@pytest.fixture
def make_client(engine, tmp_path):
    settings = Settings()
    if not settings.jwt_secret or not settings.readonly_database_url:
        pytest.skip("JWT_SECRET and READONLY_DATABASE_URL are needed")

    def _make(model):
        container = build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path),
                                    today=lambda: TODAY, assistant_model=FakeAssistantModel(),
                                    standard_model=model)  # fmt: skip
        return TestClient(create_app(container))

    return _make


@pytest.fixture
def sign_in(engine):
    emails: list[str] = []

    def _sign_in(client) -> dict[str, str]:
        email = f"{uuid.uuid4()}@test.local"
        emails.append(email)
        body = {"email": email, "password": "correct-horse"}
        assert client.post("/auth/register", json=body | {"first_name": "Sam", "gender": "female"}).status_code == 201
        return {"Authorization": f"Bearer {client.post('/auth/login', json=body).json()['access_token']}"}

    yield _sign_in
    for email in emails:
        forget_usage_by_email(engine, email)
    with engine.begin() as conn:
        for email in emails:
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


def ask(client, headers, question, **body):
    response = client.post("/assistant/ask", json={"question": question, "assistant_mode": "standard"} | body,
                           headers=headers)  # fmt: skip
    assert response.status_code == 200, response.text
    return response.json()


def budget(category="Groceries", currency="USD", limit_amount="150", year=2026, month=11):
    return {"category": category, "currency": currency, "limit_amount": limit_amount, "year": year, "month": month}


def budgets(client, headers, month="2026-11"):
    return [(b["category_name"], b["currency"], Decimal(b["limit_amount"]))
            for b in client.get("/budgets", params={"month": month}, headers=headers).json()]  # fmt: skip


def last_result(model):
    """The tool result the model was sent most recently."""
    return next(part for message in reversed(model.requests[-1].messages) for part in reversed(message.parts)
                if hasattr(part, "is_error"))  # fmt: skip


def test_a_budget_is_set_only_after_the_user_confirms_it(make_client, sign_in):
    model = ScriptedChatModel(
        calls(("t1", "propose_budget", budget(category="groceries"))), says(ASK),
        calls(("t2", "confirm_budget", budget())), says("Done: Groceries is now $150 a month from November."),
    )  # fmt: skip
    client = make_client(model)
    headers = sign_in(client)

    first = ask(client, headers, "set my groceries budget to 150 dollars")
    assert first["content"] == ASK
    assert budgets(client, headers) == []  # proposing sets nothing

    second = ask(client, headers, "yes", conversation_id=first["conversation_id"])
    context = model.requests[2].messages[-1].parts[0].text
    assert "- category 'Groceries', USD 150 a month, from 2026-11" in context  # what is waiting for the answer
    assert second["content"] == "Done: Groceries is now $150 a month from November."
    assert budgets(client, headers) == [("Groceries", "USD", Decimal("150"))]
    assert budgets(client, headers, "2026-12") == [("Groceries", "USD", Decimal("150"))]  # and the months after


def test_a_change_is_never_confirmed_in_the_answer_that_proposed_it(make_client, sign_in):
    model = ScriptedChatModel(calls(("t1", "propose_budget", budget()), ("t2", "confirm_budget", budget())), says(ASK))
    client = make_client(model)
    headers = sign_in(client)
    ask(client, headers, "set my groceries budget to 150 dollars")
    assert budgets(client, headers) == []
    result = last_result(model)
    assert result.is_error and "did not ask the user to confirm" in result.content


def test_only_the_values_the_user_was_asked_about_can_be_set(make_client, sign_in):
    model = ScriptedChatModel(
        calls(("t1", "propose_budget", budget())), says(ASK),
        calls(("t2", "confirm_budget", budget(limit_amount="1500"))), says("Sorry, I could not set it."),
    )  # fmt: skip
    client = make_client(model)
    headers = sign_in(client)
    first = ask(client, headers, "set my groceries budget to 150 dollars")
    ask(client, headers, "yes", conversation_id=first["conversation_id"])
    assert budgets(client, headers) == []
    result = last_result(model)
    assert result.is_error and "not the values the user was asked to confirm" in result.content


def test_a_proposal_is_only_answered_by_the_next_question_in_its_conversation(make_client, sign_in):
    model = ScriptedChatModel(
        calls(("t1", "propose_budget", budget())), says(ASK),
        calls(("t2", "confirm_budget", budget())), says("Sorry, I could not set it."),  # another conversation
        says("You're welcome!"),  # back in the first: the user talked about something else
        calls(("t3", "confirm_budget", budget())), says("Sorry, I could not set it."),
    )  # fmt: skip
    client = make_client(model)
    headers = sign_in(client)
    first = ask(client, headers, "set my groceries budget to 150 dollars")
    ask(client, headers, "yes")  # a new conversation, straight after the proposal
    assert last_result(model).is_error
    ask(client, headers, "thanks", conversation_id=first["conversation_id"])
    ask(client, headers, "yes", conversation_id=first["conversation_id"])
    assert last_result(model).is_error
    assert budgets(client, headers) == []


def test_a_confirmed_change_cannot_be_applied_twice(make_client, sign_in):
    model = ScriptedChatModel(
        calls(("t1", "propose_budget", budget())), says(ASK),
        calls(("t2", "confirm_budget", budget())), says("Done: Groceries is now $150 a month."),
        calls(("t3", "confirm_budget", budget())), says("Sorry, I could not set it."),
    )  # fmt: skip
    client = make_client(model)
    headers = sign_in(client)
    first = ask(client, headers, "set my groceries budget to 150 dollars")
    ask(client, headers, "yes", conversation_id=first["conversation_id"])
    client.put(f"/budgets/{_category_id(client, headers)}", json={"month": "2026-11", "limit_amount": "90"},
               headers=headers)  # the user changes it on the Budgets screen  # fmt: skip
    ask(client, headers, "yes again", conversation_id=first["conversation_id"])
    assert last_result(model).is_error
    assert budgets(client, headers) == [("Groceries", "USD", Decimal("90"))]  # the screen's change stands


def test_an_answer_that_failed_its_checks_leaves_nothing_to_confirm(make_client, sign_in):
    model = ScriptedChatModel(
        calls(("t1", "propose_budget", budget())), says("Should I set it?"), says("Should I set it?"),  # no amount
        calls(("t2", "confirm_budget", budget())), says("Sorry, I could not set it."),
    )  # fmt: skip
    client = make_client(model)
    headers = sign_in(client)
    first = ask(client, headers, "set my groceries budget to 150 dollars")
    assert first["kind"] == "error"  # never shown: the user was not asked anything
    ask(client, headers, "yes", conversation_id=first["conversation_id"])
    assert last_result(model).is_error
    assert budgets(client, headers) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (budget(month=10), "starts this month or later"),
        (budget(category="Rent"), "No category is called 'Rent'"),
        (budget(limit_amount="150 alf"), "digits only"),
    ],
)
def test_what_cannot_be_proposed_is_refused_and_nothing_is_set(make_client, sign_in, change, problem):
    model = ScriptedChatModel(calls(("t1", "propose_budget", change)), says("I could not do that."))
    client = make_client(model)
    headers = sign_in(client)
    ask(client, headers, "set a budget")
    result = last_result(model)
    assert result.is_error and problem in result.content
    assert budgets(client, headers) == []


def test_the_proposal_shows_the_budget_it_replaces(make_client, sign_in):
    model = ScriptedChatModel(calls(("t1", "propose_budget", budget(currency="LBP", limit_amount="13500000"))),
                              says("Your Groceries budget is $90. Should I make it 13,500,000 LBP from November?"))
    client = make_client(model)
    headers = sign_in(client)
    client.put(f"/budgets/{_category_id(client, headers)}", json={"month": "2026-11", "limit_amount": "90"},
               headers=headers)  # fmt: skip
    ask(client, headers, "make groceries 13.5 million lira")
    result = last_result(model)
    assert '"replaces": {"currency": "USD", "limit": "90.00"}' in result.content
    assert budgets(client, headers) == [("Groceries", "USD", Decimal("90"))]  # still only proposed


def _category_id(client, headers) -> int:
    return next(c["id"] for c in client.get("/categories", headers=headers).json() if c["name"] == "Groceries")
