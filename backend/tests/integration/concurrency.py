"""Helpers for deterministic two-transaction tests: instead of sleeping and hoping, a test waits until the
database itself reports that the other transaction is blocked on a lock."""

import threading
import time
from collections.abc import Callable

from sqlalchemy import Engine, text

TIMEOUT_SECONDS = 15


def wait_for(condition: Callable[[], bool], what: str, timeout: float = TIMEOUT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"Timed out waiting for: {what}")
        time.sleep(0.02)


def someone_waits_on_a_lock(engine: Engine) -> bool:
    """Is any other session of this database blocked on a lock right now? Tests run one at a time, so in a
    concurrency test that session is the test's other transaction."""
    with engine.connect() as conn:
        return bool(
            conn.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid() AND wait_event_type = 'Lock'"
                )
            ).scalar_one()
        )


class Background:
    """Runs a function in a thread and keeps its result or exception for the test to check."""

    def __init__(self, function: Callable[[], object], name: str = "B") -> None:
        self.result: object = None
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, args=(function,), name=name, daemon=True)
        self.thread.start()

    def _run(self, function: Callable[[], object]) -> None:
        try:
            self.result = function()
        except BaseException as exc:  # noqa: BLE001 - handed to the test
            self.error = exc

    def join(self) -> object:
        self.thread.join(TIMEOUT_SECONDS)
        assert not self.thread.is_alive(), "the background transaction did not finish"
        if self.error is not None:
            raise self.error
        return self.result

    @property
    def done(self) -> bool:
        return not self.thread.is_alive()
