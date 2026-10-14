"""One budget per category per month, whatever its currency.

A budget now counts spending in both currencies (converted at each receipt's saved rate), so a
separate USD and LBP budget for the same category and month would double up.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE budgets DROP CONSTRAINT budgets_one_per_category_month_currency")
    op.execute(
        "ALTER TABLE budgets ADD CONSTRAINT budgets_one_per_category_month UNIQUE (user_id, category_id, month)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE budgets DROP CONSTRAINT budgets_one_per_category_month")
    op.execute(
        "ALTER TABLE budgets ADD CONSTRAINT budgets_one_per_category_month_currency "
        "UNIQUE (user_id, category_id, month, currency)"
    )
