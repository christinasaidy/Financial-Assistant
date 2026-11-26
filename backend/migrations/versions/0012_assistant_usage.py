"""Assistant usage: one record per question asked, for the limits and the usage report (2026-11-23).

Limits decided with the owner on 2026-11-23: at most 30 Standard questions per user per day (Beirut time), and an
app-wide cap of $10 per month on Standard's estimated spending. Both must hold when questions arrive at the same time
and whatever is deleted later, so usage is not counted from the turns (deleting a conversation deletes its turns):
- `assistant_usage` keeps one row per question, written when its turn starts (a reservation) and completed when it
  ends: tokens, the estimated cost and the pricing version it was estimated with. Unknown stays NULL, never 0.
  It has no link to the conversation, so deleting one leaves its usage counted; deleting the account keeps the row
  (the money was spent) with user_id cleared.
- Each user reads only their own rows (row-level security). The app-wide month total is read only through
  `assistant_standard_month_spending`, which returns two numbers and nothing about any user. It runs as the owner, who
  may read every row of this table (a policy for that role only; app_user cannot use it directly).
- `ai_readonly` gets no access.

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE assistant_usage (
            turn_id             BIGINT PRIMARY KEY,
            user_id             BIGINT REFERENCES users (id) ON DELETE SET NULL,
            assistant_mode      TEXT NOT NULL,
            started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at         TIMESTAMPTZ,
            outcome             TEXT,
            model_calls         INTEGER,
            input_tokens        BIGINT,
            output_tokens       BIGINT,
            cache_write_tokens  BIGINT,
            cache_read_tokens   BIGINT,
            dollars             NUMERIC(12, 6),
            pricing_version     TEXT,
            CONSTRAINT assistant_usage_mode_valid CHECK (assistant_mode IN ('standard', 'beta')),
            CONSTRAINT assistant_usage_priced_with_version CHECK (dollars IS NULL OR pricing_version IS NOT NULL),
            CONSTRAINT assistant_usage_not_negative CHECK (dollars IS NULL OR dollars >= 0)
        )
        """
    )
    op.execute("CREATE INDEX assistant_usage_user_started_idx ON assistant_usage (user_id, started_at)")
    op.execute("CREATE INDEX assistant_usage_mode_started_idx ON assistant_usage (assistant_mode, started_at)")
    op.execute("ALTER TABLE assistant_usage ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE assistant_usage FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY assistant_usage_owner ON assistant_usage
            USING (user_id = app_user_id())
            WITH CHECK (user_id = app_user_id())
        """
    )
    # Only the table's owner (the migration role, and the function below) reads every row; it cannot write them.
    op.execute("CREATE POLICY assistant_usage_report ON assistant_usage FOR SELECT TO expense_owner USING (true)")
    op.execute(
        """
        CREATE FUNCTION assistant_standard_month_spending(since timestamptz)
        RETURNS TABLE (dollars numeric, unpriced bigint)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            SELECT COALESCE(sum(u.dollars), 0), count(*) FILTER (WHERE u.dollars IS NULL)
            FROM assistant_usage u
            WHERE u.assistant_mode = 'standard' AND u.started_at >= since
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION assistant_standard_month_spending(timestamptz) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION assistant_standard_month_spending(timestamptz) TO app_user")


def downgrade() -> None:
    op.execute("DROP FUNCTION assistant_standard_month_spending(timestamptz)")
    op.execute("DROP TABLE assistant_usage")
