from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from app.application.auth.ports import StoredCredentials
from app.domain.users.errors import EmailAlreadyRegistered
from app.domain.users.user import User

UNIQUE_VIOLATION = "23505"


class SqlUserRepository:
    """Reads and writes `users`. That table has no row-level security (login must find an
    account before the user id is known), so every query here is scoped by hand."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, email: str, password_hash: str) -> User:
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    text("INSERT INTO users (email, password_hash) VALUES (:email, :hash) RETURNING id, email"),
                    {"email": email, "hash": password_hash},
                ).one()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == UNIQUE_VIOLATION:
                raise EmailAlreadyRegistered("Email is already registered") from exc
            raise
        return User(id=row.id, email=row.email)

    def get_credentials_by_email(self, email: str) -> StoredCredentials | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, email, password_hash FROM users WHERE lower(email) = lower(:email)"),
                {"email": email},
            ).one_or_none()
        if row is None:
            return None
        return StoredCredentials(user=User(id=row.id, email=row.email), password_hash=row.password_hash)

    def get_by_id(self, user_id: int) -> User | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, email FROM users WHERE id = :id"), {"id": user_id}
            ).one_or_none()
        return User(id=row.id, email=row.email) if row else None
