"""Fill in missing exchange rates for real, and require a rate on every confirmed receipt.

Migration 0004 tried to give confirmed receipts without a rate the default of 89500, but `receipts` has
FORCE ROW LEVEL SECURITY and the migration sets no user, so that UPDATE could not see a single row and
changed nothing (found in the 2026-10-15 code review).

Here the force is switched off for the owner only for the length of this transaction, the rows are
filled in, and it is switched back on before the transaction commits. The new CHECK then makes sure a
confirmed receipt can never be without a rate again, because the assistant's USD views divide by it.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE receipts NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE receipts SET exchange_rate_used = 89500, exchange_rate_source = 'default' "
        "WHERE status = 'confirmed' AND exchange_rate_used IS NULL"
    )
    op.execute("ALTER TABLE receipts FORCE ROW LEVEL SECURITY")
    op.execute(
        "ALTER TABLE receipts ADD CONSTRAINT receipts_confirmed_has_rate "
        "CHECK (status <> 'confirmed' OR exchange_rate_used IS NOT NULL)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE receipts DROP CONSTRAINT receipts_confirmed_has_rate")
    # The rates filled in by upgrade() are left in place: they are valid data either way.
