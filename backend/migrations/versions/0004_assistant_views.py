"""The three read-only views the assistant's generated SQL may query (agreed with the user on 2026-10-15).

They live in their own schema, `assistant`, so the model's `receipts` never means the real table. The
spending rules are applied here once, so generated SQL only filters and adds up:
- only confirmed receipts;
- an item's category is its own, else its receipt's, else 'Uncategorized';
- `category_spending` also has receipts without items (whole total under the receipt's category) and a
  'Tax, discounts & rounding' row per receipt (total minus items), so it always adds up to `receipts`;
- every amount also in USD, at the receipt's saved rate (LBP per USD).

The views run with their owner's rights, and every table under them has FORCE ROW LEVEL SECURITY, so they
only ever show the rows of the user set in `app.user_id`. `ai_readonly` may read these views and nothing else.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# An amount in USD: USD amounts as they are, LBP amounts divided by the receipt's saved rate.
_USD = "CASE WHEN r.currency = 'USD' THEN {amount} ELSE {amount} / r.exchange_rate_used END"


def upgrade() -> None:
    # Receipts confirmed before rates were saved get today's default, so no USD amount is missing.
    op.execute(
        "UPDATE receipts SET exchange_rate_used = 89500, exchange_rate_source = 'default' "
        "WHERE status = 'confirmed' AND exchange_rate_used IS NULL"
    )

    op.execute("CREATE SCHEMA assistant")

    op.execute(
        f"""
        CREATE VIEW assistant.receipts AS
        SELECT r.id AS receipt_id, r.receipt_date, v.name AS vendor, r.currency, r.total,
               {_USD.format(amount="r.total")} AS total_usd
        FROM public.receipts r
        LEFT JOIN public.vendors v ON v.id = r.vendor_id
        WHERE r.status = 'confirmed'
        """
    )
    op.execute(
        f"""
        CREATE VIEW assistant.purchases AS
        SELECT ri.receipt_id, r.receipt_date, v.name AS vendor,
               ri.description AS item, ri.normalized_name AS item_name,
               COALESCE(c.name, 'Uncategorized') AS category,
               ri.quantity, ri.unit_price, ri.line_total, ri.size_amount, ri.size_unit, r.currency,
               {_USD.format(amount="ri.line_total")} AS line_total_usd
        FROM public.receipt_items ri
        JOIN public.receipts r ON r.id = ri.receipt_id
        LEFT JOIN public.vendors v ON v.id = r.vendor_id
        LEFT JOIN public.categories c ON c.id = COALESCE(ri.category_id, r.primary_category_id)
        WHERE r.status = 'confirmed'
        """
    )
    op.execute(
        f"""
        CREATE VIEW assistant.category_spending AS
        SELECT receipt_id, receipt_date, vendor, category, currency,
               line_total AS amount, line_total_usd AS amount_usd
        FROM assistant.purchases
        UNION ALL
        SELECT r.id, r.receipt_date, v.name, COALESCE(c.name, 'Uncategorized'), r.currency,
               r.total, {_USD.format(amount="r.total")}
        FROM public.receipts r
        LEFT JOIN public.vendors v ON v.id = r.vendor_id
        LEFT JOIN public.categories c ON c.id = r.primary_category_id
        WHERE r.status = 'confirmed'
          AND NOT EXISTS (SELECT 1 FROM public.receipt_items ri WHERE ri.receipt_id = r.id)
        UNION ALL
        SELECT r.id, r.receipt_date, v.name, 'Tax, discounts & rounding', r.currency,
               r.total - items.total, {_USD.format(amount="(r.total - items.total)")}
        FROM public.receipts r
        JOIN (SELECT receipt_id, SUM(line_total) AS total FROM public.receipt_items GROUP BY receipt_id) items
          ON items.receipt_id = r.id
        LEFT JOIN public.vendors v ON v.id = r.vendor_id
        WHERE r.status = 'confirmed' AND r.total <> items.total
        """
    )

    op.execute("GRANT USAGE ON SCHEMA assistant TO ai_readonly")
    op.execute("GRANT SELECT ON assistant.receipts, assistant.purchases, assistant.category_spending TO ai_readonly")


def downgrade() -> None:
    op.execute("DROP SCHEMA assistant CASCADE")
    # The rates filled in by upgrade() are left in place: they are valid data either way.
