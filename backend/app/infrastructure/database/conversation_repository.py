from sqlalchemy import Connection, text

from app.domain.assistant.conversation import DEFAULT_MODE, AssistantMode, Conversation

_SELECT = """
    SELECT c.id, c.title, c.created_at, c.assistant_mode,
           COALESCE(MAX(m.created_at), c.created_at) AS last_message_at, COUNT(m.id) AS message_count
    FROM conversations c
    LEFT JOIN messages m ON m.conversation_id = c.id
"""


class SqlConversationRepository:
    """Works on a connection already scoped to one user; rows are owned by `app_user_id()`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def create(self, title: str, mode: AssistantMode = DEFAULT_MODE) -> int:
        return self._conn.execute(
            text(
                "INSERT INTO conversations (user_id, title, assistant_mode) "
                "VALUES (app_user_id(), :title, :mode) RETURNING id"
            ),
            {"title": title, "mode": mode.value},
        ).scalar_one()

    def mode_of(self, conversation_id: int) -> AssistantMode | None:
        mode = self._conn.execute(
            text("SELECT assistant_mode FROM conversations WHERE id = :id"), {"id": conversation_id}
        ).scalar_one_or_none()
        return AssistantMode(mode) if mode else None

    def exists(self, conversation_id: int) -> bool:
        return self._conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM conversations WHERE id = :id)"), {"id": conversation_id}
        ).scalar_one()

    def hold(self, conversation_id: int) -> bool:
        # The lock a foreign key check takes: a DELETE of the conversation waits until this transaction ends.
        return self._conn.execute(
            text("SELECT 1 FROM conversations WHERE id = :id FOR KEY SHARE"), {"id": conversation_id}
        ).first() is not None

    def list_all(self) -> list[Conversation]:
        rows = self._conn.execute(text(_SELECT + " GROUP BY c.id ORDER BY last_message_at DESC, c.id DESC")).all()
        return [_to_conversation(row) for row in rows]

    def get(self, conversation_id: int) -> Conversation | None:
        row = self._conn.execute(
            text(_SELECT + " WHERE c.id = :id GROUP BY c.id"), {"id": conversation_id}
        ).one_or_none()
        return _to_conversation(row) if row else None

    def delete(self, conversation_id: int) -> bool:
        # Messages and their ratings are removed by ON DELETE CASCADE.
        return bool(
            self._conn.execute(text("DELETE FROM conversations WHERE id = :id"), {"id": conversation_id}).rowcount
        )


def _to_conversation(row) -> Conversation:
    return Conversation(
        row.id, row.title or "", row.created_at, row.last_message_at, row.message_count,
        mode=AssistantMode(row.assistant_mode),
    )  # fmt: skip
