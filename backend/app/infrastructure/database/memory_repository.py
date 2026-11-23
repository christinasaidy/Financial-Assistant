from sqlalchemy import Connection, text

from app.domain.assistant.memory import Memory, MemoryKind, alias_text
from app.domain.assistant.names import NameKind
from app.domain.users.user import Gender

_COLUMNS = ("id, kind, text, alias, target_kind, target_name, vendor_id, source_conversation_id, source_message_id, "
            "created_at, updated_at")  # fmt: skip
# A shop alias follows its vendor: renamed since, it shows the vendor's current name (the id is what was confirmed).
_SELECT = ("SELECT m.id, m.kind, m.text, m.alias, m.target_kind, COALESCE(v.name, m.target_name) AS target_name, "
           "m.vendor_id, m.source_conversation_id, m.source_message_id, m.created_at, m.updated_at "
           "FROM assistant_memories m LEFT JOIN vendors v ON v.id = m.vendor_id")  # fmt: skip


class SqlMemoryRepository:
    """The user's Standard-assistant memories (row-level security keeps them to the user set on the connection)."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def list_all(self) -> list[Memory]:
        rows = self._conn.execute(text(f"{_SELECT} ORDER BY m.id")).all()
        return [_to_memory(row) for row in rows]

    def count(self) -> int:
        return self._conn.execute(text("SELECT count(*) FROM assistant_memories")).scalar_one()

    def get(self, memory_id: int) -> Memory | None:
        row = self._conn.execute(
            text(f"{_SELECT} WHERE m.id = :id"), {"id": memory_id}
        ).one_or_none()
        return _to_memory(row) if row else None

    def find_preference(self, memory_text: str) -> Memory | None:
        row = self._conn.execute(
            text(f"{_SELECT} WHERE m.kind = 'preference' AND lower(btrim(m.text)) = lower(btrim(:text))"),
            {"text": memory_text},
        ).one_or_none()  # fmt: skip
        return _to_memory(row) if row else None

    def find_alias(self, alias: str) -> Memory | None:
        row = self._conn.execute(
            text(f"{_SELECT} WHERE m.kind = 'alias' AND lower(btrim(m.alias)) = lower(btrim(:alias))"),
            {"alias": alias},
        ).one_or_none()  # fmt: skip
        return _to_memory(row) if row else None

    def add(
        self,
        kind: MemoryKind,
        memory_text: str,
        source_conversation_id: int | None,
        source_message_id: int | None,
        alias: str | None = None,
        target_kind: NameKind | None = None,
        target_name: str | None = None,
        vendor_id: int | None = None,
    ) -> Memory | None:
        """The new memory, or None if the same preference or alias already exists (also one saved just now by
        another request: the unique indexes decide)."""
        conflict = ("(user_id, lower(btrim(alias))) WHERE kind = 'alias'" if kind is MemoryKind.ALIAS
                    else "(user_id, lower(btrim(text))) WHERE kind = 'preference'")  # fmt: skip
        row = self._conn.execute(
            text(
                "INSERT INTO assistant_memories (user_id, kind, text, alias, target_kind, target_name, vendor_id, "
                "source_conversation_id, source_message_id) VALUES (app_user_id(), :kind, :text, :alias, "
                f":target_kind, :target_name, :vendor_id, :conversation, :message) ON CONFLICT {conflict} "
                f"DO NOTHING RETURNING {_COLUMNS}"
            ),
            {"kind": kind.value, "text": memory_text, "alias": alias,
             "target_kind": target_kind.value if target_kind else None, "target_name": target_name,
             "vendor_id": vendor_id, "conversation": source_conversation_id, "message": source_message_id},
        ).one_or_none()  # fmt: skip
        return _to_memory(row) if row else None

    def update(
        self, memory_id: int, memory_text: str, target_name: str | None = None, vendor_id: int | None = None
    ) -> Memory | None:
        row = self._conn.execute(
            text(
                "UPDATE assistant_memories SET text = :text, target_name = COALESCE(:target_name, target_name), "
                "vendor_id = CASE WHEN :target_name IS NULL THEN vendor_id ELSE :vendor_id END, updated_at = now() "
                f"WHERE id = :id RETURNING {_COLUMNS}"
            ),
            {"id": memory_id, "text": memory_text, "target_name": target_name, "vendor_id": vendor_id},
        ).one_or_none()
        return _to_memory(row) if row else None

    def delete(self, memory_id: int) -> bool:
        deleted = self._conn.execute(text("DELETE FROM assistant_memories WHERE id = :id"), {"id": memory_id})
        return deleted.rowcount == 1


class SqlProfileRepository:
    """The signed-in user's own profile, read through the connection's user (users has no row-level security, so
    the query is scoped by app_user_id() by hand)."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def gender(self) -> Gender | None:
        value = self._conn.execute(text("SELECT gender FROM users WHERE id = app_user_id()")).scalar_one_or_none()
        return Gender(value) if value else None


def _to_memory(row) -> Memory:
    kind = MemoryKind(row.kind)
    target_kind = NameKind(row.target_kind) if row.target_kind else None
    return Memory(
        id=row.id,
        kind=kind,
        text=alias_text(row.alias, target_kind, row.target_name) if kind is MemoryKind.ALIAS else row.text,
        created_at=row.created_at,
        updated_at=row.updated_at,
        alias=row.alias,
        target_kind=target_kind,
        target_name=row.target_name,
        vendor_id=row.vendor_id,
        source_conversation_id=row.source_conversation_id,
        source_message_id=row.source_message_id,
    )
