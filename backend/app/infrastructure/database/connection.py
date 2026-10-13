from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, create_engine, text


def create_db_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


@contextmanager
def user_scoped_connection(engine: Engine, user_id: int) -> Iterator[Connection]:
    """A transaction in which row-level security sees `user_id` as the current user.

    `set_config(..., true)` is local to this transaction, so the setting cannot leak to the
    next request that reuses the pooled connection.
    """
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user_id)})
        yield conn
