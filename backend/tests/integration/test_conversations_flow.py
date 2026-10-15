"""Conversations through the real database. The decisions and the reopened-conversation example were
approved by the user on 2026-10-15. Do not change an expected value to make a test pass."""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.domain.assistant.conversation import AnswerDetails, AnswerKind
from app.domain.assistant.errors import ConversationNotFound, InvalidQuestion
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import user_scoped_connection
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeReceiptExtractor

QUESTION = "How much did I spend on groceries this month?"
SQL = "SELECT SUM(amount_usd) FROM category_spending WHERE category = 'Groceries'"


@pytest.fixture
def container(engine, tmp_path):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    return build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path))


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


@pytest.fixture
def sign_in(client, engine):
    emails: list[str] = []

    def _sign_in() -> tuple[dict[str, str], int]:
        email = f"{uuid.uuid4()}@test.local"
        emails.append(email)
        body = {"email": email, "password": "correct-horse"}
        assert client.post("/auth/register", json=body).status_code == 201
        result = client.post("/auth/login", json=body).json()
        return {"Authorization": f"Bearer {result['access_token']}"}, result["user"]["id"]

    yield _sign_in
    with engine.begin() as conn:
        for email in emails:
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


@pytest.fixture
def alice(sign_in):
    return sign_in()


def receipt(client, headers, total="10.00") -> int:
    body = {"receipt_date": date.today().isoformat(), "currency": "USD", "total": total}
    response = client.post("/receipts/manual", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def answer(container, user_id, conversation_id, content, receipt_ids=()):
    details = AnswerDetails(AnswerKind.ANSWER, sql=SQL, receipt_ids=tuple(receipt_ids), row_count=1, duration_ms=12)
    return container.assistant.save_answer(user_id, conversation_id, content, details)


def open_chat(client, headers, conversation_id):
    response = client.get(f"/assistant/conversations/{conversation_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- Decision 1: a conversation starts with its first question, named after it ---


def test_the_first_question_starts_a_conversation_named_after_it(container, client, alice):
    headers, alice_id = alice
    assert client.get("/assistant/conversations", headers=headers).json() == []  # no empty conversations

    saved = container.assistant.save_question(alice_id, None, f"  {QUESTION}  ")
    listed = client.get("/assistant/conversations", headers=headers).json()
    assert [(c["id"], c["title"], c["message_count"]) for c in listed] == [(saved.conversation_id, QUESTION, 1)]


def test_a_follow_up_goes_into_the_same_conversation(container, client, alice):
    headers, alice_id = alice
    first = container.assistant.save_question(alice_id, None, QUESTION)
    follow_up = container.assistant.save_question(alice_id, first.conversation_id, "and last month?")
    assert follow_up.conversation_id == first.conversation_id
    chat = open_chat(client, headers, first.conversation_id)
    assert [m["content"] for m in chat["messages"]] == [QUESTION, "and last month?"]
    assert chat["title"] == QUESTION  # the title stays the first question


def test_a_long_first_question_gives_a_60_character_title(container, client, alice):
    headers, alice_id = alice
    question = "Adde sarafet 3al akel w 3al supermarket w 3al benzine l jem3a l madye w hal jem3a kamen?"
    saved = container.assistant.save_question(alice_id, None, question)
    chat = open_chat(client, headers, saved.conversation_id)
    assert len(chat["title"]) == 60 and chat["title"].endswith("…")
    assert chat["messages"][0]["content"] == question  # the full question is kept in the chat


def test_an_empty_question_is_refused_and_creates_nothing(container, client, alice):
    headers, alice_id = alice
    with pytest.raises(InvalidQuestion):
        container.assistant.save_question(alice_id, None, "   ")
    assert client.get("/assistant/conversations", headers=headers).json() == []


# --- Decisions 2 and 3: what is saved, and reopening (the approved example) ---


def test_the_approved_example_reopening_a_conversation(container, client, alice):
    headers, alice_id = alice
    r12, r15, r18 = receipt(client, headers), receipt(client, headers), receipt(client, headers)
    saved = container.assistant.save_question(alice_id, None, QUESTION)
    content = "You spent $230.40 on Groceries this month."
    reply = answer(container, alice_id, saved.conversation_id, content, [r12, r15, r18])
    assert client.delete(f"/receipts/{r18}", headers=headers).status_code == 204  # deleted since
    rated = client.put(f"/assistant/messages/{reply.id}/rating", json={"rating": "up"}, headers=headers)
    assert rated.status_code == 204

    question, assistant = open_chat(client, headers, saved.conversation_id)["messages"]
    assert (question["role"], question["content"], question["kind"], question["rating"]) == (
        "user",
        QUESTION,
        None,
        None,
    )
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "You spent $230.40 on Groceries this month."
    assert assistant["kind"] == "answer"
    assert assistant["sql"] == SQL
    assert assistant["source_receipts"] == [
        {"receipt_id": r12, "available": True},
        {"receipt_id": r15, "available": True},
        {"receipt_id": r18, "available": False},
    ]
    assert assistant["rating"] == "up"


def test_answers_keep_their_details_without_any_rating(container, client, alice):
    headers, alice_id = alice
    saved = container.assistant.save_question(alice_id, None, QUESTION)
    answer(container, alice_id, saved.conversation_id, "You spent $12.", [])
    reply = open_chat(client, headers, saved.conversation_id)["messages"][1]
    assert (reply["kind"], reply["sql"], reply["rating"]) == ("answer", SQL, None)


def test_saved_answers_are_not_recalculated(container, client, alice):
    headers, alice_id = alice
    r1 = receipt(client, headers, total="10.00")
    saved = container.assistant.save_question(alice_id, None, QUESTION)
    answer(container, alice_id, saved.conversation_id, "You spent $10.00.", [r1])
    receipt(client, headers, total="90.00")  # spending changes afterwards
    assert open_chat(client, headers, saved.conversation_id)["messages"][1]["content"] == "You spent $10.00."


# --- Decision 4: ratings ---


def test_a_rating_can_be_changed_and_removed(container, client, alice):
    headers, alice_id = alice
    saved = container.assistant.save_question(alice_id, None, QUESTION)
    reply = answer(container, alice_id, saved.conversation_id, "You spent $12.")
    url = f"/assistant/messages/{reply.id}/rating"

    def rating():
        return open_chat(client, headers, saved.conversation_id)["messages"][1]["rating"]

    client.put(url, json={"rating": "up"}, headers=headers)
    client.put(url, json={"rating": "down"}, headers=headers)
    assert rating() == "down"  # one current rating, replaced
    assert client.delete(url, headers=headers).status_code == 204
    assert rating() is None


def test_questions_cannot_be_rated(container, client, alice):
    headers, alice_id = alice
    saved = container.assistant.save_question(alice_id, None, QUESTION)
    response = client.put(f"/assistant/messages/{saved.message_id}/rating", json={"rating": "up"}, headers=headers)
    assert response.status_code == 422


def test_only_up_or_down_is_accepted(container, client, alice):
    headers, alice_id = alice
    saved = container.assistant.save_question(alice_id, None, QUESTION)
    reply = answer(container, alice_id, saved.conversation_id, "You spent $12.")
    url = f"/assistant/messages/{reply.id}/rating"
    assert client.put(url, json={"rating": "meh"}, headers=headers).status_code == 422


# --- Decision 5: deleting a conversation ---


def test_deleting_a_conversation_removes_its_messages_and_ratings_but_not_receipts(container, client, alice, engine):
    headers, alice_id = alice
    r1 = receipt(client, headers)
    saved = container.assistant.save_question(alice_id, None, QUESTION)
    reply = answer(container, alice_id, saved.conversation_id, "You spent $10.", [r1])
    client.put(f"/assistant/messages/{reply.id}/rating", json={"rating": "down"}, headers=headers)

    assert client.delete(f"/assistant/conversations/{saved.conversation_id}", headers=headers).status_code == 204
    assert client.get(f"/assistant/conversations/{saved.conversation_id}", headers=headers).status_code == 404
    with user_scoped_connection(engine, alice_id) as conn:  # straight to the tables, as alice
        assert conn.execute(text("SELECT count(*) FROM messages WHERE conversation_id = :c"),
                            {"c": saved.conversation_id}).scalar_one() == 0  # fmt: skip
        assert conn.execute(text("SELECT count(*) FROM assistant_feedback WHERE message_id = :m"),
                            {"m": reply.id}).scalar_one() == 0  # fmt: skip
    assert client.get(f"/receipts/{r1}", headers=headers).status_code == 200


# --- Decision 6: the list ---


def test_the_list_is_newest_activity_first(container, client, alice):
    headers, alice_id = alice
    older = container.assistant.save_question(alice_id, None, "first chat")
    newer = container.assistant.save_question(alice_id, None, "second chat")
    container.assistant.save_question(alice_id, older.conversation_id, "back to the first one")
    listed = client.get("/assistant/conversations", headers=headers).json()
    assert [c["id"] for c in listed] == [older.conversation_id, newer.conversation_id]
    assert listed[0]["message_count"] == 2


# --- Users never reach each other's conversations ---


def test_users_cannot_reach_each_others_conversations(container, client, alice, sign_in):
    headers, alice_id = alice
    saved = container.assistant.save_question(alice_id, None, QUESTION)
    reply = answer(container, alice_id, saved.conversation_id, "You spent $12.")
    bob, bob_id = sign_in()

    assert client.get("/assistant/conversations", headers=bob).json() == []
    assert client.get(f"/assistant/conversations/{saved.conversation_id}", headers=bob).status_code == 404
    assert client.delete(f"/assistant/conversations/{saved.conversation_id}", headers=bob).status_code == 404
    assert client.put(f"/assistant/messages/{reply.id}/rating", json={"rating": "down"}, headers=bob).status_code == 404
    with pytest.raises(ConversationNotFound):  # knowing the id is not enough to write into it
        container.assistant.save_question(bob_id, saved.conversation_id, "injected")
    with pytest.raises(ConversationNotFound):
        container.assistant.save_answer(bob_id, saved.conversation_id, "injected", AnswerDetails(AnswerKind.ANSWER))

    chat = open_chat(client, headers, saved.conversation_id)
    assert [m["content"] for m in chat["messages"]] == [QUESTION, "You spent $12."]
    assert chat["messages"][1]["rating"] is None


def test_endpoints_need_a_token(client):
    assert client.get("/assistant/conversations").status_code == 401
    assert client.get("/assistant/conversations/1").status_code == 401
    assert client.delete("/assistant/conversations/1").status_code == 401
    assert client.put("/assistant/messages/1/rating", json={"rating": "up"}).status_code == 401
    assert client.delete("/assistant/messages/1/rating").status_code == 401
