from decimal import Decimal

from sqlalchemy import Connection, text

from app.domain.assistant.conversation import AssistantMode
from app.domain.assistant.usage import TurnUsage

# The advisory lock that Standard question starts take in turn (two int4 keys, so it can never be the same lock as
# the per-user budget lock, which uses one bigint key). Held only while a question is checked and reserved.
_STANDARD_STARTS_LOCK = (2026, 1123)
# The start of the current day or month in a time zone, as a timestamptz.
_SINCE = "(date_trunc(:period, now() AT TIME ZONE :zone) AT TIME ZONE :zone)"


class SqlUsageRepository:
    """The user's question usage (row-level security), and the app-wide Standard total through its function."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def lock_standard_starts(self) -> None:
        """Until this transaction ends, any other Standard question start waits: so two at once cannot both pass a
        limit that only one of them fits under."""
        self._conn.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"),
                           {"a": _STANDARD_STARTS_LOCK[0], "b": _STANDARD_STARTS_LOCK[1]})  # fmt: skip

    def reserve(self, turn_id: int, mode: AssistantMode) -> None:
        self._conn.execute(
            text("INSERT INTO assistant_usage (turn_id, user_id, assistant_mode) VALUES (:id, app_user_id(), :mode)"),
            {"id": turn_id, "mode": mode.value},
        )

    def finish(self, turn_id: int, outcome: str, usage: TurnUsage | None) -> None:
        values = {
            "id": turn_id,
            "outcome": outcome[:100],
            "calls": usage.model_calls if usage else None,
            "input": usage.input_tokens if usage else None,
            "output": usage.output_tokens if usage else None,
            "write": usage.cache_write_tokens if usage else None,
            "read": usage.cache_read_tokens if usage else None,
            "dollars": usage.dollars if usage else None,
            "version": usage.pricing_version if usage else None,
        }
        self._conn.execute(
            text(
                "UPDATE assistant_usage SET finished_at = now(), outcome = :outcome, model_calls = :calls, "
                "input_tokens = :input, output_tokens = :output, cache_write_tokens = :write, "
                "cache_read_tokens = :read, dollars = :dollars, pricing_version = :version "
                "WHERE turn_id = :id AND finished_at IS NULL"
            ),
            values,
        )

    def count_since(self, mode: AssistantMode, period: str, time_zone: str) -> int:
        """The user's questions in `mode` since the start of today or this month ("day" / "month") in the zone."""
        return self._conn.execute(
            text(f"SELECT count(*) FROM assistant_usage WHERE assistant_mode = :mode AND started_at >= {_SINCE}"),
            {"mode": mode.value, "period": _period(period), "zone": time_zone},
        ).scalar_one()

    def standard_month_spending(self, time_zone: str) -> tuple[Decimal, int]:
        """Every user's Standard spending this month: the known estimates, and how many questions are not priced."""
        row = self._conn.execute(
            text(f"SELECT dollars, unpriced FROM assistant_standard_month_spending({_SINCE})"),
            {"period": "month", "zone": time_zone},
        ).one()
        return Decimal(row.dollars), int(row.unpriced)


def _period(period: str) -> str:
    if period not in ("day", "month"):
        raise ValueError(period)
    return period
