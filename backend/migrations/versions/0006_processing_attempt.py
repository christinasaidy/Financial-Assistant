"""Number each attempt at reading a receipt, so only the worker that owns the current attempt may save its result.

Second code review (2026-10-16), finding 10. Claiming a receipt for reading increments `processing_attempt` and
remembers the new number; saving the draft or marking the receipt failed only happens if the receipt is still
`processing` with that same number. A receipt deleted, finished another way, or claimed again by a later attempt
(a future recovery job for receipts stuck in `processing`) therefore ignores the old worker's result.

Additive only: existing rows get 0, nothing is rewritten or removed.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE receipts ADD COLUMN processing_attempt integer NOT NULL DEFAULT 0")
    op.execute(
        "ALTER TABLE receipts ADD CONSTRAINT receipts_processing_attempt_non_negative CHECK (processing_attempt >= 0)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE receipts DROP COLUMN processing_attempt")
