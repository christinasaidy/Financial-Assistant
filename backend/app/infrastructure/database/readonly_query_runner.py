import psycopg
from sqlalchemy import Engine

from app.application.assistant.dtos import QueryResult
from app.domain.assistant.errors import QueryFailed

DEFAULT_MAX_ROWS = 200
DEFAULT_TIMEOUT_MS = 5000
DEFAULT_MAX_COLUMNS = 50
DEFAULT_MAX_RESULT_BYTES = 1_000_000  # what is kept and handed on (to the answer and the saved metadata)


class SqlReadOnlyQueryRunner:
    """Runs checked SQL through the `ai_readonly` role: a read-only transaction that sees only the
    assistant views (search_path) and only the given user's rows (row-level security).

    The database holds these limits even for SQL that never went through the checker:
    - the role can only read the three views, and the transaction is read-only;
    - the role is not allowed to call `set_config` (revoked in db/init.sql), so a query cannot switch
      to another user's id; the user is set here with SET LOCAL, which cannot appear inside a SELECT;
    - the query runs in a server-side cursor (DECLARE ... CURSOR FOR), which accepts only a single SELECT and is
      sent over the extended protocol, so the server refuses a text holding more than one command;
    - only max_rows + 1 rows are ever fetched from that cursor, so the database stops producing rows there instead
      of running the query to the end and sending everything to the driver (second code review, finding 6). This
      bounds the rows, not all the work: a query that sorts or groups still reads all of its input first.

    Size limits (third code review, 2026-10-18), and when each one acts:
    - the statement timeout bounds the time (and so, indirectly, the work) of every statement;
    - max_columns is checked on the cursor's description after DECLARE and BEFORE the one FETCH, so a query with too
      many columns produces and sends no row at all;
    - max_result_bytes is checked AFTER that FETCH, on the rows received. It only limits what is kept and handed on;
      the rows were already produced and transferred, and it cannot stop the server from building one huge value.
      What prevents huge values is the checker, before the query runs: bounded type sizes, no recursion, short SQL
      (sql_guard.py). SQL run without the checker is limited only by the role, the timeout and PostgreSQL itself.
    """

    def __init__(
        self,
        engine: Engine,
        max_rows: int = DEFAULT_MAX_ROWS,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        max_columns: int = DEFAULT_MAX_COLUMNS,
        max_result_bytes: int = DEFAULT_MAX_RESULT_BYTES,
    ) -> None:
        self._engine = engine
        self._max_rows = max_rows
        self._timeout_ms = int(timeout_ms)
        self._max_columns = max_columns
        self._max_result_bytes = max_result_bytes

    def run(self, user_id: int, sql: str) -> QueryResult:
        user_id = int(user_id)  # an int, so it is safe to write into the SET commands below
        with self._engine.connect() as conn, conn.begin():
            driver = conn.connection.driver_connection
            with driver.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                # SET LOCAL: these last only until the end of this transaction.
                cursor.execute(f"SET LOCAL app.user_id = '{user_id}'")
                cursor.execute("SET LOCAL search_path = assistant")
                cursor.execute(f"SET LOCAL statement_timeout = '{self._timeout_ms}ms'")
                try:
                    # A named (server-side) cursor, closed by the `with` before the transaction ends, on success
                    # or failure. No parameters, so "%" in ILIKE '%laban%' is never read as a placeholder.
                    with driver.cursor(name="assistant_query") as query:
                        query.execute(sql)
                        if len(query.description or []) > self._max_columns:  # known before any row is fetched
                            raise QueryFailed(f"The query returns more than {self._max_columns} columns")
                        rows = query.fetchmany(self._max_rows + 1)  # one FETCH of at most max_rows + 1 rows
                        columns = [column.name for column in query.description or []]
                except psycopg.Error as exc:
                    raise QueryFailed(str(exc).splitlines()[0]) from exc

                # Belt and braces: the query must not have changed whose rows it saw.
                cursor.execute("SELECT current_setting('app.user_id', true)")
                if cursor.fetchone()[0] != str(user_id):
                    conn.invalidate()  # never reuse this connection
                    raise QueryFailed("The query tried to change the user it runs as")
        kept = [tuple(row) for row in rows[: self._max_rows]]
        if _result_bytes(kept) > self._max_result_bytes:  # after the fetch: limits what is kept, see the class doc
            raise QueryFailed(f"The result is too large (more than {self._max_result_bytes} bytes)")
        return QueryResult(sql=sql, columns=columns, rows=kept, truncated=len(rows) > self._max_rows)


class UnavailableQueryRunner:
    """Used when READONLY_DATABASE_URL is not set: the assistant cannot run any query."""

    def run(self, user_id: int, sql: str) -> QueryResult:
        raise QueryFailed("The assistant's read-only database connection is not configured")


def _result_bytes(rows: list) -> int:
    """Roughly how much data the rows hold: text as UTF-8 bytes, other values as their text form."""
    total = 0
    for row in rows:
        for value in row:
            if isinstance(value, bytes):
                total += len(value)
            elif value is not None:
                total += len(str(value).encode())
    return total
