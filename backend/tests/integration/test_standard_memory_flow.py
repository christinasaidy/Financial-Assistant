"""The Standard assistant's memories and skills against the real database (2026-11-23): the memory endpoints, the
memory tools in a scripted Standard chat, the reply forms from the gender chosen at sign-up, and the data boundaries
(row-level security, composite foreign keys, no access for ai_readonly). AC-07, AC-11, AC-12 (forgotten memories are
not brought back), and section 13A (Standard does not run without the reviewed Arabizi pack).

Only the model is scripted, so these prove the plumbing and the rules, never what Sonnet would answer.
"""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.api.app import create_app
from app.infrastructure.config import Settings
from app.infrastructure.skills import arabizi_pack
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.integration.conftest import forget_usage_by_email
from tests.fakes import FakeAssistantModel, FakeReceiptExtractor, ScriptedChatModel, calls, says

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
def make_client(settings, tmp_path):
    def _make(model=None, beta=None):
        container = build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path),
                                    today=lambda: TODAY, assistant_model=beta or FakeAssistantModel(),
                                    standard_model=model or ScriptedChatModel())  # fmt: skip
        return TestClient(create_app(container))

    return _make


@pytest.fixture
def sign_in(engine):
    emails: list[str] = []

    def _sign_in(client, gender="prefer_not_to_say") -> tuple[dict[str, str], int]:
        email = f"{uuid.uuid4()}@test.local"
        emails.append(email)
        body = {"email": email, "password": "correct-horse"}
        response = client.post("/auth/register", json=body | {"first_name": "Sam", "gender": gender})
        assert response.status_code == 201, response.text
        result = client.post("/auth/login", json=body).json()
        return {"Authorization": f"Bearer {result['access_token']}"}, result["user"]["id"]

    yield _sign_in
    for email in emails:
        forget_usage_by_email(engine, email)
    with engine.begin() as conn:
        for email in emails:
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


def add(client, headers, vendor="Zaatar w Zeit", total="6.50"):
    body = {"vendor_name": vendor, "receipt_date": TODAY.isoformat(), "currency": "USD", "total": total,
            "primary_category_id": None, "lbp_per_usd": "89500",
            "lines": [{"description": "Manakish", "normalized_name": "manakish", "line_total": total}]}  # fmt: skip
    response = client.post("/receipts/manual", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def ask(client, headers, question, **body):
    response = client.post("/assistant/ask", json={"question": question, "assistant_mode": "standard"} | body,
                           headers=headers)  # fmt: skip
    assert response.status_code == 200, response.text
    return response.json()


def save(kind="preference", text="", alias="", target_kind="", target_name=""):
    return {"kind": kind, "text": text, "alias": alias, "target_kind": target_kind, "target_name": target_name}


# --- the memory endpoints ---


def test_memories_are_listed_added_corrected_and_forgotten(make_client, sign_in):
    client = make_client()
    headers, _ = sign_in(client)
    add(client, headers)

    created = client.post("/assistant/memories", json={"kind": "preference", "text": "Keep your answers short"},
                          headers=headers)  # fmt: skip
    assert created.status_code == 201
    again = client.post("/assistant/memories", json={"kind": "preference", "text": "keep your answers SHORT "},
                        headers=headers)  # fmt: skip
    assert (again.status_code, again.json()["id"]) == (200, created.json()["id"])  # nothing new saved

    alias = client.post("/assistant/memories", json={"kind": "alias", "alias": "zwz", "target_kind": "vendor",
                                                     "target_name": "Zaatar w Zeit"}, headers=headers).json()
    assert alias["text"] == '"zwz" means the shop "Zaatar w Zeit"'  # fmt: skip

    memory_id = created.json()["id"]
    patched = client.patch(f"/assistant/memories/{memory_id}", json={"text": "Answer in one sentence"},
                           headers=headers)  # fmt: skip
    assert patched.json()["text"] == "Answer in one sentence"
    assert [m["text"] for m in client.get("/assistant/memories", headers=headers).json()] == [
        "Answer in one sentence", '"zwz" means the shop "Zaatar w Zeit"']
    assert client.delete(f"/assistant/memories/{memory_id}", headers=headers).status_code == 204
    assert client.delete(f"/assistant/memories/{memory_id}", headers=headers).status_code == 404
    assert len(client.get("/assistant/memories", headers=headers).json()) == 1


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ({"kind": "preference", "text": "I spent $250 this month"}, "Amounts are not remembered"),
        ({"kind": "alias", "alias": "zwz", "target_kind": "vendor", "target_name": "zaatar w zeit"},
         "is not one of the user's vendor names"),  # not the exact spelling
        ({"kind": "alias", "alias": "zwz", "target_kind": "vendor", "target_name": "Nowhere"},
         "is not one of the user's vendor names"),
        ({"kind": "alias", "alias": "zwz", "target_name": "Zaatar w Zeit"}, "needs target_kind"),
    ],
)  # fmt: skip
def test_what_cannot_be_remembered_is_refused(make_client, sign_in, body, problem):
    client = make_client()
    headers, _ = sign_in(client)
    add(client, headers)
    response = client.post("/assistant/memories", json=body, headers=headers)
    assert response.status_code == 422 and problem in response.text


def test_an_alias_with_the_same_name_for_another_target_is_refused(make_client, sign_in):
    client = make_client()
    headers, _ = sign_in(client)
    add(client, headers)
    add(client, headers, vendor="Spinneys")
    first = {"kind": "alias", "alias": "zwz", "target_kind": "vendor", "target_name": "Zaatar w Zeit"}
    assert client.post("/assistant/memories", json=first, headers=headers).status_code == 201
    response = client.post("/assistant/memories", json=first | {"target_name": "Spinneys"}, headers=headers)
    assert response.status_code == 422 and "already saved" in response.text


def test_a_shop_alias_follows_the_shop_when_it_is_renamed(make_client, sign_in, as_user):
    client = make_client()
    headers, user_id = sign_in(client)
    add(client, headers)
    client.post("/assistant/memories", json={"kind": "alias", "alias": "zwz", "target_kind": "vendor",
                                             "target_name": "Zaatar w Zeit"}, headers=headers)  # fmt: skip
    with as_user(user_id) as conn:
        conn.execute(text("UPDATE vendors SET name = 'Zaatar W Zeit Hamra' WHERE name = 'Zaatar w Zeit'"))
    (memory,) = client.get("/assistant/memories", headers=headers).json()
    assert memory["target_name"] == "Zaatar W Zeit Hamra"
    assert memory["text"] == '"zwz" means the shop "Zaatar W Zeit Hamra"'


def test_at_most_fifty_memories(make_client, sign_in):
    client = make_client()
    headers, _ = sign_in(client)
    for i in range(50):
        assert client.post("/assistant/memories", json={"kind": "preference", "text": f"Rule number {i}"},
                           headers=headers).status_code == 201  # fmt: skip
    response = client.post("/assistant/memories", json={"kind": "preference", "text": "One more"}, headers=headers)
    assert response.status_code == 409


# --- isolation (AC-07) ---


def test_another_users_memories_cannot_be_seen_changed_or_forgotten(make_client, sign_in):
    client = make_client()
    alice, _ = sign_in(client)
    bob, _ = sign_in(client)
    memory_id = client.post("/assistant/memories", json={"kind": "preference", "text": "Keep it short"},
                            headers=alice).json()["id"]  # fmt: skip
    assert client.get("/assistant/memories", headers=bob).json() == []
    assert client.patch(f"/assistant/memories/{memory_id}", json={"text": "Mine now"}, headers=bob).status_code == 404
    assert client.delete(f"/assistant/memories/{memory_id}", headers=bob).status_code == 404
    assert [m["text"] for m in client.get("/assistant/memories", headers=alice).json()] == ["Keep it short"]
    assert client.get("/assistant/memories").status_code == 401


def test_an_alias_cannot_point_at_another_users_shop(make_client, sign_in):
    client = make_client()
    alice, _ = sign_in(client)
    bob, _ = sign_in(client)
    add(client, bob, vendor="Bob's Garage")
    response = client.post("/assistant/memories", json={"kind": "alias", "alias": "garage", "target_kind": "vendor",
                                                        "target_name": "Bob's Garage"}, headers=alice)  # fmt: skip
    assert response.status_code == 422


def test_the_database_refuses_links_to_another_users_rows(make_client, sign_in, as_user):
    client = make_client()
    _, alice = sign_in(client)
    bob_headers, bob = sign_in(client)
    add(client, bob_headers, vendor="Bob's Garage")
    with as_user(bob) as conn:
        vendor_id = conn.execute(text("SELECT id FROM vendors")).scalar_one()
        conversation_id = conn.execute(text(
            "INSERT INTO conversations (user_id, title) VALUES (app_user_id(), 'x') RETURNING id")).scalar_one()
    for column, value in [("vendor_id", vendor_id), ("source_conversation_id", conversation_id)]:
        kind = ("'alias', 'a', 'vendor', 'x'" if column == "vendor_id" else "'preference', NULL, NULL, NULL")
        with pytest.raises(DBAPIError), as_user(alice) as conn:  # composite foreign key: (id, user_id)
            conn.execute(text(f"INSERT INTO assistant_memories (user_id, kind, alias, target_kind, target_name, "
                              f"text, {column}) VALUES (app_user_id(), {kind}, 'remember', :v)"), {"v": value})


def test_ai_readonly_cannot_read_memories(settings):
    engine = create_engine(settings.readonly_database_url)
    with pytest.raises(DBAPIError, match="permission denied"), engine.connect() as conn:
        conn.execute(text("SELECT * FROM assistant_memories"))


# --- memories in a Standard chat (AC-11) ---


def test_a_memory_saved_in_chat_is_in_the_next_questions_context_until_forgotten(make_client, sign_in):
    model = ScriptedChatModel(
        calls(("t1", "save_memory", save("alias", alias="zwz", target_kind="vendor", target_name="Zaatar w Zeit"))),
        says("Saved: zwz means Zaatar w Zeit."),
        says("Hi!"),
    )
    beta = FakeAssistantModel(sql=["REPLY: hi"])
    client = make_client(model, beta)
    headers, _ = sign_in(client)
    add(client, headers)

    first = ask(client, headers, "remember that zwz means zaatar w zeit")
    assert first["content"] == "Saved: zwz means Zaatar w Zeit."
    (memory,) = client.get("/assistant/memories", headers=headers).json()
    assert memory["from_conversation_id"] == first["conversation_id"]  # it records where it was asked

    ask(client, headers, "hi", conversation_id=first["conversation_id"])
    context = model.requests[-1].messages[-1].parts[0].text
    assert f'- memory {memory["id"]} (alias): "zwz" means the shop "Zaatar w Zeit"' in context

    # Beta never sees memories: its prompt is its training contract.
    client.post("/assistant/ask", json={"question": "hi", "assistant_mode": "beta"}, headers=headers)
    assert "zwz" not in beta.sql_prompts[0] and "Saved memories" not in beta.sql_prompts[0]

    # Forgotten in chat, it is gone from the next question's context (AC-12: never brought back).
    model.script += [calls(("t2", "forget_memory", {"memory_id": memory["id"]})), says("Done, I forgot it."),
                     says("Hi again!")]  # fmt: skip
    ask(client, headers, "forget zwz", conversation_id=first["conversation_id"])
    ask(client, headers, "hi", conversation_id=first["conversation_id"])
    assert "zwz" not in model.requests[-1].messages[-1].parts[0].text
    assert client.get("/assistant/memories", headers=headers).json() == []


def test_deleting_the_conversation_keeps_its_memories(make_client, sign_in):
    model = ScriptedChatModel(calls(("t1", "save_memory", save(text="Keep your answers short"))), says("Saved."))
    client = make_client(model)
    headers, _ = sign_in(client)
    conversation_id = ask(client, headers, "remember: keep your answers short")["conversation_id"]
    assert client.delete(f"/assistant/conversations/{conversation_id}", headers=headers).status_code == 204
    (memory,) = client.get("/assistant/memories", headers=headers).json()
    assert (memory["text"], memory["from_conversation_id"]) == ("Keep your answers short", None)


def test_a_failed_memory_save_is_told_to_the_model_and_nothing_is_saved(make_client, sign_in):
    model = ScriptedChatModel(calls(("t1", "save_memory", save(text="I spent $250 this month"))),
                              says("I can't remember amounts, but I can always check your receipts."))  # fmt: skip
    client = make_client(model)
    headers, _ = sign_in(client)
    ask(client, headers, "remember I spent $250")
    result = model.requests[1].messages[-1].parts[0]
    assert result.is_error and "Amounts are not remembered" in result.content
    assert client.get("/assistant/memories", headers=headers).json() == []


# --- reply forms and the Arabizi pack ---


@pytest.mark.parametrize(("gender", "forms"), [("female", "the woman forms"), ("male", "the man forms"),
                                               ("prefer_not_to_say", "the neutral forms")])  # fmt: skip
def test_the_reply_forms_follow_the_gender_chosen_at_sign_up(make_client, sign_in, gender, forms):
    model = ScriptedChatModel(says("Hi!"))
    client = make_client(model)
    headers, _ = sign_in(client, gender=gender)
    ask(client, headers, "hi")
    assert f"only if you reply in Arabizi: {forms}" in model.requests[0].messages[-1].parts[0].text


def test_every_standard_answer_carries_the_arabizi_skill_and_records_its_version(make_client, sign_in, as_user):
    model = ScriptedChatModel(says("Hi!"))
    client = make_client(model)
    headers, user_id = sign_in(client)
    ask(client, headers, "hi")
    assert "## Skill: lebanese_arabizi" in model.requests[0].system
    with as_user(user_id) as conn:
        execution = conn.execute(text("SELECT execution FROM assistant_turns")).scalar_one()
    assert execution["skills"]["lebanese_arabizi"].startswith("arabizi-pack-generator-1-")


def test_standard_is_unavailable_without_the_reviewed_pack(make_client, sign_in, monkeypatch):
    monkeypatch.setattr(arabizi_pack, "EXPECTED_FINGERPRINT", "0" * 64)  # as if the pack had changed unreviewed
    model = ScriptedChatModel()
    client = make_client(model)
    headers, _ = sign_in(client)
    modes = {m["mode"]: m for m in client.get("/assistant/modes", headers=headers).json()}
    assert modes["standard"]["available"] is False
    body = ask(client, headers, "hi")
    assert body["kind"] == "error" and model.requests == []  # never answered without her rulings
