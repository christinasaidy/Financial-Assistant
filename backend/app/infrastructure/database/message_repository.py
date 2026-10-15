import json

from sqlalchemy import Connection, text

from app.domain.assistant.conversation import AnswerDetails, AnswerKind, Message, MessageRole, Rating


class SqlMessageRepository:
    """Messages have no user_id: row-level security lets a user see only the messages of their own
    conversations, so a message or conversation id from someone else simply does not exist here."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def add(
        self, conversation_id: int, role: MessageRole, content: str, details: AnswerDetails | None = None
    ) -> Message:
        row = self._conn.execute(
            text(
                "INSERT INTO messages (conversation_id, role, content, metadata) "
                "VALUES (:conversation_id, :role, :content, CAST(:metadata AS jsonb)) RETURNING id, created_at"
            ),
            {
                "conversation_id": conversation_id,
                "role": role.value,
                "content": content,
                "metadata": json.dumps(_to_metadata(details)) if details else None,
            },
        ).one()
        return Message(row.id, role, content, row.created_at, details)

    def list_for(self, conversation_id: int) -> list[Message]:
        rows = self._conn.execute(
            text(
                """
                SELECT m.id, m.role, m.content, m.metadata, m.created_at, f.rating
                FROM messages m
                LEFT JOIN assistant_feedback f ON f.message_id = m.id
                WHERE m.conversation_id = :id
                ORDER BY m.created_at, m.id
                """
            ),
            {"id": conversation_id},
        ).all()
        return [
            Message(
                id=row.id,
                role=MessageRole(row.role),
                content=row.content,
                created_at=row.created_at,
                details=_from_metadata(row.metadata),
                rating=Rating.from_score(row.rating) if row.rating is not None else None,
            )
            for row in rows
        ]

    def role_of(self, message_id: int) -> MessageRole | None:
        role = self._conn.execute(
            text("SELECT role FROM messages WHERE id = :id"), {"id": message_id}
        ).scalar_one_or_none()
        return MessageRole(role) if role else None


def _to_metadata(details: AnswerDetails) -> dict[str, object]:
    return {
        "kind": details.kind.value,
        "sql": details.sql,
        "receipt_ids": list(details.receipt_ids),
        "row_count": details.row_count,
        "duration_ms": details.duration_ms,
    }


def _from_metadata(metadata: dict | None) -> AnswerDetails | None:
    if not metadata:
        return None
    return AnswerDetails(
        kind=AnswerKind(metadata["kind"]),
        sql=metadata.get("sql"),
        receipt_ids=tuple(metadata.get("receipt_ids") or ()),
        row_count=metadata.get("row_count"),
        duration_ms=metadata.get("duration_ms"),
    )
