from sqlalchemy import Connection, text

from app.domain.categories.category import Category


class SqlCategoryRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def list_all(self) -> list[Category]:
        # Row-level security already limits this to shared categories and the user's own.
        rows = self._conn.execute(
            text("SELECT id, name, user_id IS NULL AS is_shared FROM categories ORDER BY is_shared DESC, name")
        ).all()
        return [Category(id=row.id, name=row.name, is_shared=row.is_shared) for row in rows]
