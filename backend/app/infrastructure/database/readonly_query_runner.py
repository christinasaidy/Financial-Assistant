import psycopg
from sqlalchemy import Engine

from app.application.assistant.dtos import QueryResult
from app.domain.assistant.errors import QueryFailed

DEFAULT_MAX_ROWS = 200
DEFAULT_TIMEOUT_MS = 5000


class SqlReadOnlyQueryRunner:
    """Runs checked SQL through the `ai_readonly` role: a read-only transaction that sees only the
    assistant views (search_path) and only the given user's rows (row-level security).

    The database holds these limits even for SQL that never went through the checker:
    - the role can only read the three views, and the transaction is read-only;
    - the role is not allowed to call `set_config` (revoked in db/init.sql), so a query cannot switch
      to another user's id; the user is set here with SET LOCAL, which cannot appear inside a SELECT;
    - the query is sent as a prepared statement, which the server refuses if it holds more than one command.
    """

    def __init__(self, engine: Engine, max_rows: int = DEFAULT_MAX_ROWS, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> None:
        self._engine = engine
        self._max_rows = max_rows
        self._timeout_ms = int(timeout_ms)

    def run(self, user_id: int, sql: str) -> QueryResult:
        user_id = int(user_id)  # an int, so it is safe to write into the SET commands below
        with self._engine.connect() as conn, conn.begin():
            cursor = conn.connection.driver_connection.cursor()
            try:
                cursor.execute("SET TRANSACTION READ ONLY")
                # SET LOCAL: these last only until the end of this transaction.
                cursor.execute(f"SET LOCAL app.user_id = '{user_id}'")
                cursor.execute("SET LOCAL search_path = assistant")
                cursor.execute(f"SET LOCAL statement_timeout = '{self._timeout_ms}ms'")
                try:
                    # No parameters, so "%" in ILIKE '%laban%' is never read as a placeholder; prepare=True,
                    # so the server refuses a text holding more than one command.
                    cursor.execute(sql, prepare=True)
                    rows = cursor.fetchmany(self._max_rows + 1)
                    columns = [column.name for column in cursor.description or []]
                except psycopg.Error as exc:
                    raise QueryFailed(str(exc).splitlines()[0]) from exc

                # Belt and braces: the query must not have changed whose rows it saw.
                cursor.execute("SELECT current_setting('app.user_id', true)")
                if cursor.fetchone()[0] != str(user_id):
                    conn.invalidate()  # never reuse this connection
                    raise QueryFailed("The query tried to change the user it runs as")
            finally:
                cursor.close()
        return QueryResult(
            sql=sql,
            columns=columns,
            rows=[tuple(row) for row in rows[: self._max_rows]],
            truncated=len(rows) > self._max_rows,
        )


class UnavailableQueryRunner:
    """Used when READONLY_DATABASE_URL is not set: the assistant cannot run any query."""

    def run(self, user_id: int, sql: str) -> QueryResult:
        raise QueryFailed("The assistant's read-only database connection is not configured")
