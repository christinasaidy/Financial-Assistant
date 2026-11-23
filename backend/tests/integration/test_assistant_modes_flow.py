"""The two assistant modes and the turn rules, through the real API and database (2026-11-23).

Both workflows are fakes: Beta's model gives the replies set below, and the Standard workflow answers every question
with a fixed reply. So these tests prove the routing, the saved mode, the turn rules (one running turn per
conversation, retries with an Idempotency-Key, abandoned turns, deletion while answering) and the isolation of turns,
never what a real model would answer.
"""

import threading
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.api.app import create_app
from app.domain.assistant import answer as answers
from app.domain.assistant.conversation import AssistantMode
from app.domain.assistant.errors import ConversationNotFound, TurnInProgress, TurnSuperseded
from app.infrastructure.config import Settings
from app.infrastructure.language_model.unavailable_assistant_model import UnavailableAssistantModel
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.integration.conftest import forget_usage_by_email
from tests.fakes import FakeAssistantModel, FakeReceiptExtractor, FakeStandardAssistant

TODAY = date(2026, 11, 23)


@pytest.fixture
def settings(engine):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    if not settings.readonly_database_url:
        pytest.skip("READONLY_DATABASE_URL is not set (the ai_readonly role's connection)")
    return settings


@pytest.fixture
def beta():
    return FakeAssistantModel()


@pytest.fixture
def standard():
    return FakeStandardAssistant()


def _container(settings, tmp_path, beta, standard):
    return build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path),
                           today=lambda: TODAY, assistant_model=beta, standard_assistant=standard)  # fmt: skip


@pytest.fixture
def container(settings, tmp_path, beta, standard):
    return _container(settings, tmp_path, beta, standard)


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


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


@pytest.fixture
def alice(client, sign_in):
    return sign_in(client)


@pytest.fixture
def bob(client, sign_in):
    return sign_in(client)


def post(client, headers, question, conversation_id=None, mode=None, key=None):
    body: dict = {"question": question, "conversation_id": conversation_id}
    if mode is not None:
        body["assistant_mode"] = mode
    return client.post("/assistant/ask", json=body, headers=headers | ({"Idempotency-Key": key} if key else {}))


def messages_of(client, headers, conversation_id) -> list[tuple[str, str]]:
    detail = client.get(f"/assistant/conversations/{conversation_id}", headers=headers).json()
    return [(m["role"], m["content"]) for m in detail["messages"]]


def turns_of(as_user, user_id, conversation_id) -> list[tuple[str, str | None]]:
    with as_user(user_id) as conn:
        return [tuple(row) for row in conn.execute(
            text("SELECT status, problem FROM assistant_turns WHERE conversation_id = :id ORDER BY id"),
            {"id": conversation_id})]  # fmt: skip


# --- AC-01: the mode is chosen once, saved, and routes every later question ---


def test_a_standard_conversation_is_answered_by_standard_only(client, beta, standard, alice):
    headers, user_id = alice
    first = post(client, headers, "hello", mode="standard")
    assert first.status_code == 200, first.text
    answer = first.json()
    assert (answer["assistant_mode"], answer["content"], answer["kind"]) == ("standard", "Standard answer", "reply")
    assert answer["models"] == ["fake-standard-model"]

    follow_up = post(client, headers, "and last month?", answer["conversation_id"])  # mode left out
    assert follow_up.json()["assistant_mode"] == "standard"

    assert beta.sql_prompts == [] and beta.answer_prompts == []  # Beta's model was never called
    assert [r.question for r in standard.requests] == ["hello", "and last month?"]
    assert all(r.user_id == user_id for r in standard.requests)  # the user comes from the sign-in
    # The second request carries the first exchange as history, without the new question itself.
    assert [(m.role.value, m.content) for m in standard.requests[1].history] == [
        ("user", "hello"), ("assistant", "Standard answer")]  # fmt: skip
    listed = client.get("/assistant/conversations", headers=headers).json()
    assert [c["assistant_mode"] for c in listed] == ["standard"]


def test_a_new_conversation_without_a_mode_is_beta(client, beta, standard, alice):
    headers, _ = alice
    beta.sql_replies = ["REPLY: Hi!"]
    answer = post(client, headers, "hi").json()
    assert (answer["assistant_mode"], answer["content"]) == ("beta", "Hi!")
    assert answer["models"] == ["fake-sql-model"]
    assert standard.requests == []
    detail = client.get(f"/assistant/conversations/{answer['conversation_id']}", headers=headers).json()
    assert detail["assistant_mode"] == "beta"


def test_an_unknown_mode_is_refused(client, alice):
    headers, _ = alice
    assert post(client, headers, "hi", mode="gemini").status_code == 422


# --- AC-02: a conversation never switches modes ---


def test_asking_a_beta_conversation_in_standard_mode_is_refused_with_nothing_saved(client, beta, standard, alice):
    headers, _ = alice
    beta.sql_replies = ["REPLY: Hi!"]
    conversation_id = post(client, headers, "hi", mode="beta").json()["conversation_id"]
    before = messages_of(client, headers, conversation_id)

    refused = post(client, headers, "how much did I spend?", conversation_id, mode="standard")

    assert refused.status_code == 409
    assert messages_of(client, headers, conversation_id) == before
    assert standard.requests == [] and len(beta.sql_prompts) == 1


def test_asking_a_standard_conversation_in_beta_mode_is_refused(client, beta, standard, alice):
    headers, _ = alice
    conversation_id = post(client, headers, "hello", mode="standard").json()["conversation_id"]
    assert post(client, headers, "again", conversation_id, mode="beta").status_code == 409
    assert len(standard.requests) == 1 and beta.sql_prompts == []


# --- AC-04: each mode is available or not on its own, and neither answers for the other ---


def test_without_standard_its_conversations_are_not_available_and_beta_is_never_used(settings, tmp_path, sign_in):
    beta = FakeAssistantModel(sql=["REPLY: Hi!"])
    client = TestClient(create_app(_container(settings, tmp_path, beta, None)))
    headers, _ = sign_in(client)

    modes = {m["mode"]: m for m in client.get("/assistant/modes", headers=headers).json()}
    assert modes["standard"] == {"mode": "standard", "available": False, "models": [], "reason": "not_configured"}
    assert modes["beta"]["available"] is True

    answer = post(client, headers, "hello", mode="standard").json()
    assert (answer["kind"], answer["content"], answer["assistant_mode"]) == ("error", answers.NOT_AVAILABLE, "standard")
    assert beta.sql_prompts == []  # no fallback to Beta
    assert post(client, headers, "hi").json()["content"] == "Hi!"  # Beta itself still works


def test_without_beta_standard_still_works(settings, tmp_path, sign_in):
    standard = FakeStandardAssistant()
    client = TestClient(create_app(_container(settings, tmp_path, UnavailableAssistantModel(), standard)))
    headers, _ = sign_in(client)

    modes = {m["mode"]: m for m in client.get("/assistant/modes", headers=headers).json()}
    assert modes["beta"]["available"] is False and modes["standard"]["available"] is True

    assert post(client, headers, "hello", mode="standard").json()["content"] == "Standard answer"
    beta_answer = post(client, headers, "hello").json()
    assert (beta_answer["kind"], beta_answer["content"]) == ("error", answers.NOT_AVAILABLE)
    assert len(standard.requests) == 1  # no fallback to Standard


def test_the_modes_need_a_signed_in_user(client):
    assert client.get("/assistant/modes").status_code == 401


# --- AC-13: a retried request is answered once ---


def test_a_retried_request_returns_the_first_answer(client, standard, alice):
    headers, _ = alice
    key = str(uuid.uuid4())
    first = post(client, headers, "hello", mode="standard", key=key).json()
    again = post(client, headers, "hello", mode="standard", key=key).json()

    assert again == first
    assert len(standard.requests) == 1
    expected = [("user", "hello"), ("assistant", "Standard answer")]
    assert messages_of(client, headers, first["conversation_id"]) == expected
    assert len(client.get("/assistant/conversations", headers=headers).json()) == 1  # no second conversation


def test_a_key_reused_for_another_question_is_refused(client, standard, alice):
    headers, _ = alice
    key = str(uuid.uuid4())
    post(client, headers, "hello", mode="standard", key=key)
    assert post(client, headers, "something else", mode="standard", key=key).status_code == 422
    assert post(client, headers, "hello", mode="beta", key=key).status_code == 422
    assert len(standard.requests) == 1


def test_keys_belong_to_one_user(client, standard, alice, bob):
    key = str(uuid.uuid4())
    mine = post(client, alice[0], "hello", mode="standard", key=key).json()
    theirs = post(client, bob[0], "hello", mode="standard", key=key).json()  # the same key, another user
    assert theirs["conversation_id"] != mine["conversation_id"]
    assert len(standard.requests) == 2


def test_an_empty_or_huge_key_is_refused(client, alice):
    headers, _ = alice
    assert post(client, headers, "hello", key="   ").status_code == 422
    assert post(client, headers, "hello", key="k" * 201).status_code == 422


# --- AC-13 / AC-14: one turn at a time, failures and abandoned turns ---


def _ask_in_thread(container, user_id, conversation_id, question, **kwargs):
    outcome: dict = {}

    def run():
        try:
            outcome["result"] = container.assistant.ask(user_id, conversation_id, question, **kwargs)
        except Exception as exc:  # noqa: BLE001 - the test inspects it
            outcome["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def test_a_second_question_while_one_is_answered_is_refused_with_nothing_saved(container, client, standard, alice):
    headers, user_id = alice
    conversation_id = post(client, headers, "first", mode="standard").json()["conversation_id"]
    standard.hold, standard.started = True, threading.Event()
    thread, outcome = _ask_in_thread(container, user_id, conversation_id, "second")
    assert standard.started.wait(10)

    busy = post(client, headers, "third", conversation_id)
    assert busy.status_code == 409
    standard.hold = False  # the held answer keeps waiting; new ones are answered at once
    other = post(client, headers, "another chat", mode="standard")  # other conversations are not blocked
    standard.release.set()
    thread.join(10)

    assert other.status_code == 200
    assert "error" not in outcome
    assert messages_of(client, headers, conversation_id) == [
        ("user", "first"), ("assistant", "Standard answer"), ("user", "second"), ("assistant", "Standard answer")]
    assert post(client, headers, "fourth", conversation_id).status_code == 200  # free again afterwards


def test_the_same_new_request_twice_at_once_makes_one_conversation(container, standard, alice):
    _, user_id = alice
    key = str(uuid.uuid4())
    standard.hold = True
    first, first_outcome = _ask_in_thread(container, user_id, None, "hello", mode=AssistantMode.STANDARD,
                                          idempotency_key=key)  # fmt: skip
    assert standard.started.wait(10)
    with pytest.raises(TurnInProgress):  # the retry arrives while the first is still answering
        container.assistant.ask(user_id, None, "hello", mode=AssistantMode.STANDARD, idempotency_key=key)
    standard.release.set()
    first.join(10)

    replay = container.assistant.ask(user_id, None, "hello", mode=AssistantMode.STANDARD, idempotency_key=key)
    assert replay.answer.id == first_outcome["result"].answer.id
    assert len(container.assistant.list_conversations(user_id)) == 1
    assert len(standard.requests) == 1


def test_a_crash_keeps_the_question_fails_the_turn_and_frees_the_conversation(container, client, as_user, standard,
                                                                              alice):  # fmt: skip
    headers, user_id = alice
    conversation_id = post(client, headers, "first", mode="standard").json()["conversation_id"]
    standard.fail = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        container.assistant.ask(user_id, conversation_id, "second")
    assert turns_of(as_user, user_id, conversation_id) == [("completed", None), ("failed", "RuntimeError")]
    assert messages_of(client, headers, conversation_id)[-1] == ("user", "second")

    standard.fail = None
    assert post(client, headers, "third", conversation_id).status_code == 200


def test_a_failed_keyed_request_cannot_be_replayed(container, standard, alice):
    _, user_id = alice
    key = str(uuid.uuid4())
    standard.fail = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        container.assistant.ask(user_id, None, "hello", mode=AssistantMode.STANDARD, idempotency_key=key)
    standard.fail = None
    with pytest.raises(Exception, match="failed without an answer"):
        container.assistant.ask(user_id, None, "hello", mode=AssistantMode.STANDARD, idempotency_key=key)


def test_an_abandoned_turn_is_given_up_and_its_late_answer_is_not_saved(settings, tmp_path, as_user, beta, sign_in):
    standard = FakeStandardAssistant()
    container = build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path),
                                today=lambda: TODAY, assistant_model=beta, standard_assistant=standard)  # fmt: skip
    client = TestClient(create_app(container))
    headers, user_id = sign_in(client)
    conversation_id = post(client, headers, "first", mode="standard").json()["conversation_id"]

    standard.hold = True
    standard.started = threading.Event()
    stuck, stuck_outcome = _ask_in_thread(container, user_id, conversation_id, "stuck")
    assert standard.started.wait(10)
    with as_user(user_id) as conn:  # as if it had started long ago and its worker had stopped
        conn.execute(text("UPDATE assistant_turns SET started_at = now() - interval '1 hour' "
                          "WHERE conversation_id = :id AND status = 'running'"), {"id": conversation_id})  # fmt: skip

    standard.hold = False  # the next question is answered at once
    assert post(client, headers, "after the restart", conversation_id).status_code == 200
    standard.release.set()
    stuck.join(10)

    assert isinstance(stuck_outcome.get("error"), TurnSuperseded)
    assert turns_of(as_user, user_id, conversation_id) == [
        ("completed", None), ("failed", "abandoned"), ("completed", None)]  # fmt: skip
    assert [c for r, c in messages_of(client, headers, conversation_id) if r == "assistant"] == ["Standard answer"] * 2


def test_deleting_the_conversation_while_answering_does_not_bring_it_back(container, client, standard, alice):
    headers, user_id = alice
    conversation_id = post(client, headers, "first", mode="standard").json()["conversation_id"]
    standard.hold, standard.started = True, threading.Event()
    thread, outcome = _ask_in_thread(container, user_id, conversation_id, "second")
    assert standard.started.wait(10)

    assert client.delete(f"/assistant/conversations/{conversation_id}", headers=headers).status_code == 204
    standard.release.set()
    thread.join(10)

    assert isinstance(outcome.get("error"), ConversationNotFound)
    assert client.get("/assistant/conversations", headers=headers).json() == []


# --- AC-07: turns are the user's own ---


def test_turns_are_invisible_and_unwritable_across_users(container, client, as_user, alice, bob):
    alice_headers, alice_id = alice
    _, bob_id = bob
    conversation_id = post(client, alice_headers, "hello", mode="standard").json()["conversation_id"]
    with as_user(alice_id) as conn:
        question_id = conn.execute(text("SELECT question_message_id FROM assistant_turns WHERE conversation_id = :c"),
                                   {"c": conversation_id}).scalar_one()  # fmt: skip

    with as_user(bob_id) as conn:
        assert conn.execute(text("SELECT count(*) FROM assistant_turns")).scalar_one() == 0
        assert conn.execute(text("UPDATE assistant_turns SET status = 'failed', finished_at = now()")).rowcount == 0

    # Bob writing a turn into Alice's conversation: refused (row-level security, then the composite foreign key).
    for owner in ("app_user_id()", str(alice_id)):
        with pytest.raises(DBAPIError):
            with as_user(bob_id) as conn:
                conn.execute(text(f"INSERT INTO assistant_turns (user_id, conversation_id, question_message_id, "
                                  f"assistant_mode) VALUES ({owner}, :c, :q, 'standard')"),
                             {"c": conversation_id, "q": question_id})  # fmt: skip


def test_a_turn_cannot_point_at_a_message_of_another_conversation(client, as_user, alice):
    headers, user_id = alice
    one = post(client, headers, "one", mode="standard").json()["conversation_id"]
    two = post(client, headers, "two", mode="standard").json()["conversation_id"]
    with as_user(user_id) as conn:
        question_of_two = conn.execute(
            text("SELECT question_message_id FROM assistant_turns WHERE conversation_id = :c"), {"c": two}
        ).scalar_one()
    with pytest.raises(DBAPIError):
        with as_user(user_id) as conn:
            conn.execute(text("INSERT INTO assistant_turns (user_id, conversation_id, question_message_id, "
                              "assistant_mode) VALUES (app_user_id(), :c, :q, 'standard')"),
                         {"c": one, "q": question_of_two})  # fmt: skip


def test_the_assistant_read_only_role_cannot_see_turns(settings):
    from sqlalchemy import create_engine

    readonly = create_engine(settings.readonly_database_url)
    with pytest.raises(DBAPIError, match="permission denied"):
        with readonly.connect() as conn:
            conn.execute(text("SELECT count(*) FROM public.assistant_turns"))
    readonly.dispose()
