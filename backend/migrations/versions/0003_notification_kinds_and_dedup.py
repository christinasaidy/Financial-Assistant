"""Notification kinds agreed on 2026-10-14, and a key that stops the same notification being sent twice.

`dedup_key` names one notification, e.g. "budget_near:5:2026-10" (category 5, October) or
"receipt_ready:42". The database refuses a second row with the same key for the same user.
`summary` and `reminder` are reserved for the scheduled notifications planned for later.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE notifications DROP CONSTRAINT notifications_kind_valid")
    op.execute(
        """
        ALTER TABLE notifications ADD CONSTRAINT notifications_kind_valid CHECK (kind IN (
            'budget_near', 'budget_limit_reached', 'pace_warning',
            'receipt_ready', 'receipt_failed', 'summary', 'reminder'
        ))
        """
    )
    op.execute("ALTER TABLE notifications ADD COLUMN dedup_key TEXT")
    op.execute(
        "CREATE UNIQUE INDEX notifications_user_dedup_key ON notifications (user_id, dedup_key) "
        "WHERE dedup_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX notifications_user_dedup_key")
    op.execute("ALTER TABLE notifications DROP COLUMN dedup_key")
    op.execute("ALTER TABLE notifications DROP CONSTRAINT notifications_kind_valid")
    op.execute(
        "ALTER TABLE notifications ADD CONSTRAINT notifications_kind_valid "
        "CHECK (kind IN ('budget_threshold', 'pace_warning', 'summary'))"
    )
