from sqlalchemy import Connection, text

from app.domain.assistant.conversation import Rating


class SqlFeedbackRepository:
    """One current rating per assistant answer. The database only accepts ratings on assistant
    messages (a foreign key pinned to role 'assistant'), and only on the user's own conversations."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def set(self, message_id: int, rating: Rating) -> None:
        self._conn.execute(
            text(
                """
                INSERT INTO assistant_feedback (message_id, rating) VALUES (:id, :rating)
                ON CONFLICT (message_id) DO UPDATE SET rating = EXCLUDED.rating, updated_at = now()
                """
            ),
            {"id": message_id, "rating": rating.score},
        )

    def clear(self, message_id: int) -> bool:
        return bool(
            self._conn.execute(
                text("DELETE FROM assistant_feedback WHERE message_id = :id"), {"id": message_id}
            ).rowcount
        )
