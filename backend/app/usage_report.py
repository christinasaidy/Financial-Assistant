"""The assistant's usage for a month, for the app's owner (2026-11-23): questions, tokens and estimated cost per mode.

    python -m app.usage_report                 # this month (Beirut time)
    python -m app.usage_report --month 2026-11

Runs as the owner role (MIGRATION_DATABASE_URL), the only one that may read every user's usage rows. Users are shown
by id only, never by email. Tokens a provider did not report are "unknown", never 0; costs are estimates from the
configured prices (STANDARD_PRICE_*), each made with the pricing version saved on its row. Questions still running,
or that failed before reporting, have no estimate and count at the reserve against the monthly cap.
"""

import argparse
import sys
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, create_engine, text

from app.infrastructure.config import Settings

_MONTH = """
    SELECT assistant_mode, count(*) AS questions, count(*) FILTER (WHERE dollars IS NOT NULL) AS priced,
           sum(dollars) AS dollars, sum(input_tokens) AS input_tokens, count(input_tokens) AS with_tokens,
           sum(output_tokens) AS output_tokens, sum(cache_write_tokens) AS cache_write_tokens,
           sum(cache_read_tokens) AS cache_read_tokens, count(DISTINCT user_id) AS users
    FROM assistant_usage WHERE started_at >= :start AND started_at < :end
    GROUP BY assistant_mode ORDER BY assistant_mode
"""
_TOP_USERS = """
    SELECT user_id, count(*) AS questions, sum(dollars) AS dollars
    FROM assistant_usage WHERE assistant_mode = 'standard' AND started_at >= :start AND started_at < :end
    GROUP BY user_id ORDER BY count(*) DESC, user_id LIMIT 10
"""


def report(engine: Engine, month: date, time_zone: str, reserve: Decimal) -> str:
    zone = ZoneInfo(time_zone)
    start = datetime(month.year, month.month, 1, tzinfo=zone)
    end = datetime(month.year + month.month // 12, month.month % 12 + 1, 1, tzinfo=zone)
    with engine.connect() as conn:
        rows = conn.execute(text(_MONTH), {"start": start, "end": end}).all()
        top = conn.execute(text(_TOP_USERS), {"start": start, "end": end}).all()
    lines = [f"Assistant usage, {month:%B %Y} ({time_zone})"]
    if not rows:
        return "\n".join([*lines, "No questions."])
    for row in rows:
        unpriced = row.questions - row.priced
        lines.append(f"\n{row.assistant_mode}: {row.questions} questions from {row.users} users")
        if row.with_tokens:
            lines.append(f"  tokens ({row.with_tokens} questions reported them): input {row.input_tokens}, "
                         f"output {row.output_tokens}, cache write {row.cache_write_tokens}, "
                         f"cache read {row.cache_read_tokens}")  # fmt: skip
        else:
            lines.append("  tokens: unknown (not reported)")
        if row.assistant_mode == "standard":
            known = row.dollars or Decimal(0)
            lines.append(f"  estimated cost: ${known:.4f} for {row.priced} questions; {unpriced} without an estimate "
                         f"(counted at ${reserve} each against the cap: ${known + reserve * unpriced:.2f})")
    if top:
        lines.append("\nStandard questions per user (id): " + ", ".join(
            f"{r.user_id if r.user_id is not None else 'deleted'}: {r.questions}" for r in top))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.usage_report", description=__doc__.splitlines()[0])
    parser.add_argument("--month", help="YYYY-MM (default: this month)")
    args = parser.parse_args(argv)
    settings = Settings()
    if not settings.migration_database_url:
        print("MIGRATION_DATABASE_URL (the owner role) is not set", file=sys.stderr)
        return 1
    today = datetime.now(ZoneInfo(settings.assistant_time_zone)).date()
    month = date.fromisoformat(f"{args.month}-01") if args.month else today.replace(day=1)
    print(report(create_engine(settings.migration_database_url), month, settings.assistant_time_zone,
                 settings.standard_assistant_question_reserve_dollars))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
