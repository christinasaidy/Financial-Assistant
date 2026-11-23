"""Usage records and the Standard limits against the real database (2026-11-23): one record per question, kept when
conversations or accounts are deleted; 30 Standard questions per user per day and a $10 app-wide monthly cap, both
holding when questions arrive at the same time (AC-13, AC-14, AC-18, AC-19); each user sees only their own counts.

The models are fakes, so the costs are the fakes' reported tokens priced with the configured prices: no paid call.
The cap is app-wide, so its tests set it just above the database's current spending (other test runs' included).
"""

import threading
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.api.app import create_app
from app.domain.assistant import answer as answers
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import user_scoped_connection
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeAssistantModel, FakeReceiptExtractor, FakeStandardAssistant, ScriptedChatModel, says
from tests.integration.conftest import forget_usage_by_email

TODAY = date(2026, 11, 23)
RESERVE = Decimal("0.50")


@pytest.fixture
def make_client(engine, tmp_path):
    def _make(standard=None, model=None, **limits):
        settings = Settings(**limits)
        if not settings.jwt_secret or not settings.readonly_database_url:
            pytest.skip("JWT_SECRET and READONLY_DATABASE_URL are needed")
        container = build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path),
                                    today=lambda: TODAY, assistant_model=FakeAssistantModel(sql=["REPLY: hi"] * 50),
                                    standard_assistant=standard, standard_model=model)  # fmt: skip
        return TestClient(create_app(container))

    return _make


@pytest.fixture
def sign_in(engine):
    emails: list[str] = []

    def _sign_in(client) -> tuple[dict[str, str], int]:
        email = f"{uuid.uuid4()}@test.local"
        emails.append(email)
        body = {"email": email, "password": "correct-horse"}
        assert client.post("/auth/register", json=body | {"first_name": "Sam", "gender": "male"}).status_code == 201
        result = client.post("/auth/login", json=body).json()
        return {"Authorization": f"Bearer {result['access_token']}"}, result["user"]["id"]

    yield _sign_in
    for email in emails:
        forget_usage_by_email(engine, email)
    with engine.begin() as conn:
        for email in emails:
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


def ask(client, headers, question="hi", mode="standard", **body):
    return client.post("/assistant/ask", json={"question": question, "assistant_mode": mode} | body, headers=headers)


def usage_rows(engine, user_id):
    with user_scoped_connection(engine, user_id) as conn:
        return conn.execute(text("SELECT * FROM assistant_usage ORDER BY turn_id")).all()


def month_spending(engine, user_id) -> tuple[Decimal, int]:
    with user_scoped_connection(engine, user_id) as conn:
        row = conn.execute(text("SELECT * FROM assistant_standard_month_spending("
                                "date_trunc('month', now() AT TIME ZONE 'Asia/Beirut') AT TIME ZONE 'Asia/Beirut')"
                                )).one()  # fmt: skip
    return Decimal(row.dollars), int(row.unpriced)


# --- what is recorded ---


def test_every_question_is_recorded_with_its_tokens_and_estimated_cost(make_client, sign_in, engine):
    model = ScriptedChatModel(says("Hi!"))  # reports 10 input and 5 output tokens
    client = make_client(model=model)
    headers, user_id = sign_in(client)
    assert ask(client, headers).status_code == 200
    assert ask(client, headers, mode="beta").status_code == 200
    standard, beta = usage_rows(engine, user_id)
    assert (standard.assistant_mode, standard.outcome, standard.model_calls) == ("standard", "answered", 1)
    assert (standard.input_tokens, standard.output_tokens) == (10, 5)
    assert standard.dollars == Decimal("0.000070")  # (10 * $2 + 5 * $10) per million
    assert standard.pricing_version == "anthropic-claude-sonnet-5-5-2026-11-23"
    # Beta's model reports no tokens: unknown, never 0, and no cost estimate.
    assert (beta.assistant_mode, beta.input_tokens, beta.dollars, beta.finished_at is not None) == ("beta", None,
                                                                                                    None, True)


def test_usage_is_kept_when_the_conversation_or_the_account_is_deleted(make_client, sign_in, engine, as_user):
    client = make_client(standard=FakeStandardAssistant())
    headers, user_id = sign_in(client)
    conversation_id = ask(client, headers).json()["conversation_id"]
    assert client.delete(f"/assistant/conversations/{conversation_id}", headers=headers).status_code == 204
    assert len(usage_rows(engine, user_id)) == 1  # deleting the chat does not give the question back
    assert client.get("/assistant/usage", headers=headers).json()["today"] == {"standard": 1, "beta": 0}

    spent_before = month_spending(engine, user_id)
    with engine.begin() as conn:  # the account goes: the spending stays in the app's total, without the user
        turn_id = usage_rows(engine, user_id)[0].turn_id
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    other_headers, other = sign_in(client)
    assert month_spending(engine, other) == spent_before
    owner = Settings().migration_database_url
    if owner:  # the owner role sees the row, without the user
        with create_engine(owner).connect() as conn:
            assert conn.execute(text("SELECT user_id FROM assistant_usage WHERE turn_id = :t"),
                                {"t": turn_id}).scalar_one() is None  # fmt: skip
    # The row stays (nobody can delete it now): the fake reported $0, so it changes no cap.


def test_a_crashed_question_has_no_estimate_and_counts_at_the_reserve(make_client, sign_in, engine):
    standard = FakeStandardAssistant()
    standard.fail = RuntimeError("the workflow crashed")
    client = TestClient(make_client(standard=standard).app, raise_server_exceptions=False)
    headers, user_id = sign_in(client)
    before = month_spending(engine, user_id)
    assert ask(client, headers).status_code == 500
    (row,) = usage_rows(engine, user_id)
    assert (row.dollars, row.outcome) == (None, "failed: RuntimeError")
    assert month_spending(engine, user_id) == (before[0], before[1] + 1)


# --- 30 Standard questions per user per day ---


def test_past_the_daily_limit_a_standard_question_is_refused_and_nothing_saved(make_client, sign_in):
    client = make_client(standard=FakeStandardAssistant(),
                         standard_assistant_daily_questions_per_user=2)  # fmt: skip
    headers, _ = sign_in(client)
    first = ask(client, headers).json()
    assert ask(client, headers, conversation_id=first["conversation_id"]).status_code == 200
    usage = client.get("/assistant/usage", headers=headers).json()
    assert (usage["standard_daily_limit"], usage["standard_left_today"]) == (2, 0)

    refused = ask(client, headers)
    assert refused.status_code == 429 and "limit" in refused.json()["detail"]
    assert len(client.get("/assistant/conversations", headers=headers).json()) == 1  # nothing new saved
    modes = {m["mode"]: m for m in client.get("/assistant/modes", headers=headers).json()}
    assert (modes["standard"]["available"], modes["standard"]["reason"]) == (False, "daily_limit")
    assert ask(client, headers, mode="beta").status_code == 200  # Beta is not limited


def test_the_daily_limit_is_per_user(make_client, sign_in):
    client = make_client(standard=FakeStandardAssistant(), standard_assistant_daily_questions_per_user=1)
    alice, _ = sign_in(client)
    bob, _ = sign_in(client)
    assert ask(client, alice).status_code == 200
    assert ask(client, alice).status_code == 429
    assert ask(client, bob).status_code == 200
    assert client.get("/assistant/usage", headers=bob).json()["today"] == {"standard": 1, "beta": 0}


def test_questions_at_the_same_moment_cannot_all_pass_the_daily_limit(make_client, sign_in):
    """Eight questions at once, in eight conversations, with room for three: the start lock lets exactly three in."""
    client = make_client(standard=FakeStandardAssistant(), standard_assistant_daily_questions_per_user=3)
    headers, _ = sign_in(client)
    go = threading.Barrier(8)
    codes: list[int] = []

    def one(i):
        go.wait()
        codes.append(ask(client, headers, f"question {i}").status_code)

    threads = [threading.Thread(target=one, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert sorted(codes) == [200] * 3 + [429] * 5


# --- the app-wide monthly cap ---


def test_past_the_monthly_cap_standard_answers_not_available_without_calling_the_model(make_client, sign_in, engine):
    model = ScriptedChatModel()
    probe = make_client(model=model)
    headers, user_id = sign_in(probe)
    spent, unpriced = month_spending(engine, user_id)
    cap = spent + RESERVE * unpriced + RESERVE / 2  # no room for one more question's reserve
    client = make_client(model=model, standard_assistant_monthly_cap_dollars=str(cap))

    body = ask(client, headers).json()
    assert (body["kind"], body["content"], body["assistant_mode"]) == ("error", answers.NOT_AVAILABLE, "standard")
    assert model.requests == []  # nothing was sent to the provider
    (row,) = usage_rows(engine, user_id)
    assert (row.outcome, row.dollars, row.model_calls) == ("monthly_cap", Decimal(0), 0)
    modes = {m["mode"]: m for m in client.get("/assistant/modes", headers=headers).json()}
    assert (modes["standard"]["available"], modes["standard"]["reason"]) == (False, "monthly_cap")
    assert ask(client, headers, mode="beta").json()["content"] == "hi"  # Beta keeps working


def test_with_room_under_the_cap_questions_are_answered(make_client, sign_in, engine):
    model = ScriptedChatModel(says("Hi!"))
    probe = make_client(model=model)
    headers, user_id = sign_in(probe)
    spent, unpriced = month_spending(engine, user_id)
    client = make_client(model=model, standard_assistant_monthly_cap_dollars=str(spent + RESERVE * (unpriced + 2)))
    assert ask(client, headers).json()["content"] == "Hi!"


def test_a_question_still_running_is_reserved_against_the_cap(make_client, sign_in, engine):
    """Room for exactly one question at the reserve: while it runs (its cost not known yet), a second is capped."""
    standard = FakeStandardAssistant()
    standard.hold = True
    probe = make_client(standard=standard)
    headers, user_id = sign_in(probe)
    spent, unpriced = month_spending(engine, user_id)
    client = make_client(standard=standard,
                         standard_assistant_monthly_cap_dollars=str(spent + RESERVE * (unpriced + 1)))  # fmt: skip
    first: list = []
    worker = threading.Thread(target=lambda: first.append(ask(client, headers, "first")))
    worker.start()
    assert standard.started.wait(10)
    try:
        second = ask(client, headers, "second").json()
        assert second["content"] == answers.NOT_AVAILABLE
    finally:
        standard.release.set()
        worker.join(10)
    assert first[0].json()["content"] == "Standard answer"


# --- isolation and transactions ---


def test_a_user_sees_only_their_own_usage(make_client, sign_in, engine):
    client = make_client(standard=FakeStandardAssistant())
    alice, alice_id = sign_in(client)
    bob, bob_id = sign_in(client)
    ask(client, alice)
    ask(client, alice)
    assert client.get("/assistant/usage", headers=bob).json()["this_month"] == {"standard": 0, "beta": 0}
    assert usage_rows(engine, bob_id) == []
    with user_scoped_connection(engine, bob_id) as conn:  # nor can Bob change Alice's rows
        assert conn.execute(text("UPDATE assistant_usage SET dollars = 0")).rowcount == 0
    assert len(usage_rows(engine, alice_id)) == 2
    assert client.get("/assistant/usage").status_code == 401


def test_ai_readonly_cannot_read_usage_or_the_total(settings_readonly):
    with pytest.raises(DBAPIError, match="permission denied"), settings_readonly.connect() as conn:
        conn.execute(text("SELECT * FROM assistant_usage"))
    with pytest.raises(DBAPIError, match="permission denied"), settings_readonly.connect() as conn:
        conn.execute(text("SELECT * FROM assistant_standard_month_spending(now())"))


@pytest.fixture
def settings_readonly(engine):
    url = Settings().readonly_database_url
    if not url:
        pytest.skip("READONLY_DATABASE_URL is not set")
    return create_engine(url)


def test_no_database_transaction_is_open_while_the_model_answers(make_client, sign_in, engine):
    standard = FakeStandardAssistant()
    standard.hold = True
    client = make_client(standard=standard)
    headers, _ = sign_in(client)
    worker = threading.Thread(target=lambda: ask(client, headers))
    worker.start()
    try:
        assert standard.started.wait(10)
        with engine.connect() as conn:
            open_transactions = conn.execute(text(
                "SELECT count(*) FROM pg_stat_activity WHERE usename = current_user AND pid <> pg_backend_pid() "
                "AND state LIKE 'idle in transaction%'")).scalar_one()  # fmt: skip
        assert open_transactions == 0
    finally:
        standard.release.set()
        worker.join(10)


def test_the_owner_report_totals_every_users_questions_by_id_only(make_client, sign_in):
    from app.usage_report import report

    owner = Settings().migration_database_url
    if not owner:
        pytest.skip("MIGRATION_DATABASE_URL (the owner role) is not set")
    client = make_client(standard=FakeStandardAssistant())
    headers, user_id = sign_in(client)
    ask(client, headers)
    text_report = report(create_engine(owner), date.today().replace(day=1), "Asia/Beirut", RESERVE)
    assert "standard:" in text_report and f"{user_id}:" in text_report
    assert "@" not in text_report  # users by id, never by email
