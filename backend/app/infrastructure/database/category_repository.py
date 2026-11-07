from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.domain.categories.category import Category
from app.domain.categories.errors import CategoryAlreadyExists

UNIQUE_VIOLATION = "23505"


class SqlCategoryRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def list_all(self) -> list[Category]:
        # Row-level security already limits this to shared categories and the user's own.
        rows = self._conn.execute(
            text("SELECT id, name, user_id IS NULL AS is_shared FROM categories ORDER BY is_shared DESC, name")
        ).all()
        return [Category(id=row.id, name=row.name, is_shared=row.is_shared) for row in rows]

    def add(self, name: str) -> Category:
        try:
            with self._conn.begin_nested():  # a savepoint, so a duplicate doesn't abort the transaction
                category_id = self._conn.execute(
                    text("INSERT INTO categories (user_id, name) VALUES (app_user_id(), :name) RETURNING id"),
                    {"name": name},
                ).scalar_one()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == UNIQUE_VIOLATION:  # categories_user_name_key
                raise CategoryAlreadyExists(f"There is already a category called {name}") from exc
            raise
        return Category(id=category_id, name=name, is_shared=False)
