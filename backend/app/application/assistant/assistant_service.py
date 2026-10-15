from app.application.assistant.dtos import QueryResult
from app.application.assistant.interfaces import ReadOnlyQueryRunner, SqlGuard


class AssistantService:
    """Answers spending questions. So far it only has the safe way to run generated SQL; the question
    flow (question -> SQL -> answer) and conversations are built on top of `run_query`."""

    def __init__(self, guard: SqlGuard, runner: ReadOnlyQueryRunner) -> None:
        self._guard = guard
        self._runner = runner

    def run_query(self, user_id: int, sql: str) -> QueryResult:
        """Check generated SQL, then run it as the read-only role, limited to this user's rows.
        Two independent layers: the guard refuses anything unsafe, and the database role could
        not do harm even if something got past it."""
        return self._runner.run(user_id, self._guard.check(sql))
