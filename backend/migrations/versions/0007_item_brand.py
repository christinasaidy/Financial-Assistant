"""An optional brand on each receipt line, also shown in the assistant's `purchases` view.

Approved by the user on 2026-10-16 (branch feature/better-item-names). `normalized_name` is now the generic product
type ("spaghetti"), so the maker is kept separately ("barilla"), in lower-case Latin letters, so that questions such
as "Barilla spaghetti five months ago vs now" or price comparisons between the same product at two shops work even
when the receipt prints the brand in Arabic or abbreviated. Empty when no brand is printed.

`brand` is added as the LAST column of `assistant.purchases` (CREATE OR REPLACE VIEW can only append), so every
existing column, the grant to ai_readonly and the `category_spending` view built on it stay as they were. This view
is the schema the assistant's dataset is written against; it was changed before any dataset was written.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# An amount in USD, as in 0004: USD as it is, LBP divided by the receipt's saved rate.
_USD = "CASE WHEN r.currency = 'USD' THEN {amount} ELSE {amount} / r.exchange_rate_used END"

# The purchases view of 0004, with room for extra columns at the end.
_PURCHASES = f"""
    SELECT ri.receipt_id, r.receipt_date, v.name AS vendor,
           ri.description AS item, ri.normalized_name AS item_name,
           COALESCE(c.name, 'Uncategorized') AS category,
           ri.quantity, ri.unit_price, ri.line_total, ri.size_amount, ri.size_unit, r.currency,
           {_USD.format(amount="ri.line_total")} AS line_total_usd{{extra}}
    FROM public.receipt_items ri
    JOIN public.receipts r ON r.id = ri.receipt_id
    LEFT JOIN public.vendors v ON v.id = r.vendor_id
    LEFT JOIN public.categories c ON c.id = COALESCE(ri.category_id, r.primary_category_id)
    WHERE r.status = 'confirmed'
"""

# The category_spending view of 0004, unchanged; needed only to rebuild it on downgrade.
_CATEGORY_SPENDING = f"""
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


def upgrade() -> None:
    op.execute("ALTER TABLE receipt_items ADD COLUMN brand text")
    op.execute("ALTER TABLE receipt_items ADD CONSTRAINT receipt_items_brand_not_blank CHECK (btrim(brand) <> '')")
    op.execute("CREATE OR REPLACE VIEW assistant.purchases AS " + _PURCHASES.format(extra=", ri.brand"))


def downgrade() -> None:
    # A view cannot lose a column in place, so both views are rebuilt as 0004 made them.
    op.execute("DROP VIEW assistant.category_spending")
    op.execute("DROP VIEW assistant.purchases")
    op.execute("CREATE VIEW assistant.purchases AS " + _PURCHASES.format(extra=""))
    op.execute("CREATE VIEW assistant.category_spending AS " + _CATEGORY_SPENDING)
    op.execute("GRANT SELECT ON assistant.purchases, assistant.category_spending TO ai_readonly")
    op.execute("ALTER TABLE receipt_items DROP COLUMN brand")
