"""AC-03: conversations saved before the two modes (migration 0010) open exactly as before, as Beta, keeping the
models that really answered them.

This test downgrades the database to 0009 and upgrades it again, so it only runs on a throwaway database, when
ALLOW_MIGRATION_TESTS=1 is set (never on the development database: see PROGRESS.md, "To test migrations safely").
"""

import os
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.infrastructure.config import Settings
from app.infrastructure.security.token_service import JwtTokenService
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeAssistantModel, FakeReceiptExtractor

BACKEND_DIR = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    os.environ.get("ALLOW_MIGRATION_TESTS") != "1",
    reason="downgrades the schema: set ALLOW_MIGRATION_TESTS=1 on a throwaway database only",
)

OLD_METADATA = (
    '{"kind": "answer", "sql": "SELECT 1", "receipt_ids": [987654321], "row_count": 1, "duration_ms": 1234, '
    '"attempts": [{"step": "sql", "model": "gemini-3.5-flash-lite", "output": "SELECT 1", "problem": null}, '
    '{"step": "answer", "model": "gemini-3.5-flash-lite", "output": "You spent $8.00.", "problem": null}], '
    '"columns": null, "rows": null}'
)


def _alembic(*args: str) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    getattr(command, args[0])(config, *args[1:])


def test_old_conversations_reopen_unchanged_as_beta(engine, as_user, make_user, tmp_path):
    settings = Settings()
    _alembic("downgrade", "0009")
    try:
        user_id = make_user()
        with as_user(user_id) as conn:
            conversation_id = conn.execute(text(
                "INSERT INTO conversations (user_id, title) VALUES (app_user_id(), 'How much?') RETURNING id"
            )).scalar_one()  # fmt: skip
            conn.execute(text("INSERT INTO messages (conversation_id, role, content) VALUES (:c, 'user', 'How much?')"),
                         {"c": conversation_id})  # fmt: skip
            answer_id = conn.execute(text(
                "INSERT INTO messages (conversation_id, role, content, metadata) "
                "VALUES (:c, 'assistant', 'You spent $8.00.', CAST(:m AS jsonb)) RETURNING id"
            ), {"c": conversation_id, "m": OLD_METADATA}).scalar_one()  # fmt: skip
            conn.execute(text("INSERT INTO assistant_feedback (message_id, rating) VALUES (:m, 1)"), {"m": answer_id})
    finally:
        _alembic("upgrade", "head")

    model = FakeAssistantModel(sql=["REPLY: Hi again!"])
    container = build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path),
                                today=lambda: date(2026, 11, 23), assistant_model=model)  # fmt: skip
    view = container.assistant.open_conversation(user_id, conversation_id)

    assert view.conversation.mode.value == "beta"
    expected = [("user", "How much?"), ("assistant", "You spent $8.00.")]
    assert [(m.role.value, m.content) for m in view.messages] == expected
    old = view.messages[1]
    assert old.rating.value == "up"
    assert [(s.receipt_id, s.available) for s in old.source_receipts] == [(987654321, False)]
    assert [a.model for a in old.details.attempts] == ["gemini-3.5-flash-lite"] * 2  # never relabelled
    assert (old.details.sql, old.details.row_count, old.details.duration_ms) == ("SELECT 1", 1, 1234)

    # Through the API the old answer is labelled with the model that really wrote it, in the Beta workflow.
    client = TestClient(create_app(container))
    token = JwtTokenService(settings.jwt_secret).issue(user_id).token  # the test user has no password
    detail = client.get(f"/assistant/conversations/{conversation_id}", headers={"Authorization": f"Bearer {token}"})
    body = detail.json()
    assert body["assistant_mode"] == "beta"
    assert body["messages"][1]["models"] == ["gemini-3.5-flash-lite"]

    # It can be asked again, in Beta, and the old exchange is the history.
    result = container.assistant.ask(user_id, conversation_id, "hi")
    assert (result.mode.value, result.answer.content) == ("beta", "Hi again!")
    assert "How much?" in model.sql_prompts[0]
