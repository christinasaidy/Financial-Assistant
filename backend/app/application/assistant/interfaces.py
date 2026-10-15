from typing import Protocol

from app.application.assistant.dtos import QueryResult


class SqlGuard(Protocol):
    def check(self, sql: str) -> str:
        """Return the SQL that may run (rebuilt from what was checked), or raise UnsafeQuery."""


class ReadOnlyQueryRunner(Protocol):
    def run(self, user_id: int, sql: str) -> QueryResult:
        """Run already-checked SQL as the read-only assistant role, seeing only this user's rows.
        Raises QueryFailed if the database cannot run it."""
