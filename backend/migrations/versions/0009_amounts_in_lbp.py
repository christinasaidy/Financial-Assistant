"""Every amount in the assistant's views also in LBP, at the receipt's saved rate (approved by the user on 2026-11-23).

Each confirmed receipt already saves `exchange_rate_used` (LBP per USD; required since 0005), and the views already
give every amount in USD with it. So a question "in lira" ("bel lira", "bl lira") can be answered like one "in
dollars": LBP amounts as they are, USD amounts times the receipt's own saved rate. Before this, a dollar receipt
had no LBP value the assistant could read.

`total_lbp`, `line_total_lbp` and `amount_lbp` are added as the LAST column of each view (CREATE OR REPLACE VIEW can
only append), so every existing column and the grant to ai_readonly stay as they were. No table or data changes.

Revision ID: 0009
Revises: 0008 (0008_user_first_name_and_gender, branch feature/user-profile)
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# An amount in USD, as in 0004 / 0007, and the same amount in LBP: LBP as it is, USD times the receipt's saved rate.
_USD = "CASE WHEN r.currency = 'USD' THEN {amount} ELSE {amount} / r.exchange_rate_used END"
_LBP = "CASE WHEN r.currency = 'LBP' THEN {amount} ELSE {amount} * r.exchange_rate_used END"

_RECEIPTS = f"""
    SELECT r.id AS receipt_id, r.receipt_date, v.name AS vendor, r.currency, r.total,
           {_USD.format(amount="r.total")} AS total_usd{{extra}}
    FROM public.receipts r
    LEFT JOIN public.vendors v ON v.id = r.vendor_id
    WHERE r.status = 'confirmed'
"""

_PURCHASES = f"""
    SELECT ri.receipt_id, r.receipt_date, v.name AS vendor,
           ri.description AS item, ri.normalized_name AS item_name,
           COALESCE(c.name, 'Uncategorized') AS category,
           ri.quantity, ri.unit_price, ri.line_total, ri.size_amount, ri.size_unit, r.currency,
           {_USD.format(amount="ri.line_total")} AS line_total_usd, ri.brand{{extra}}
    FROM public.receipt_items ri
    JOIN public.receipts r ON r.id = ri.receipt_id
    LEFT JOIN public.vendors v ON v.id = r.vendor_id
    LEFT JOIN public.categories c ON c.id = COALESCE(ri.category_id, r.primary_category_id)
    WHERE r.status = 'confirmed'
"""

_CATEGORY_SPENDING = f"""
    SELECT receipt_id, receipt_date, vendor, category, currency,
           line_total AS amount, line_total_usd AS amount_usd{{extra_items}}
    FROM assistant.purchases
    UNION ALL
    SELECT r.id, r.receipt_date, v.name, COALESCE(c.name, 'Uncategorized'), r.currency,
           r.total, {_USD.format(amount="r.total")}{{extra_whole}}
    FROM public.receipts r
    LEFT JOIN public.vendors v ON v.id = r.vendor_id
    LEFT JOIN public.categories c ON c.id = r.primary_category_id
    WHERE r.status = 'confirmed'
      AND NOT EXISTS (SELECT 1 FROM public.receipt_items ri WHERE ri.receipt_id = r.id)
    UNION ALL
    SELECT r.id, r.receipt_date, v.name, 'Tax, discounts & rounding', r.currency,
           r.total - items.total, {_USD.format(amount="(r.total - items.total)")}{{extra_rest}}
    FROM public.receipts r
    JOIN (SELECT receipt_id, SUM(line_total) AS total FROM public.receipt_items GROUP BY receipt_id) items
      ON items.receipt_id = r.id
    LEFT JOIN public.vendors v ON v.id = r.vendor_id
    WHERE r.status = 'confirmed' AND r.total <> items.total
"""


def upgrade() -> None:
    op.execute("CREATE OR REPLACE VIEW assistant.receipts AS "
               + _RECEIPTS.format(extra=f", {_LBP.format(amount='r.total')} AS total_lbp"))
    op.execute("CREATE OR REPLACE VIEW assistant.purchases AS "
               + _PURCHASES.format(extra=f", {_LBP.format(amount='ri.line_total')} AS line_total_lbp"))
    op.execute("CREATE OR REPLACE VIEW assistant.category_spending AS " + _CATEGORY_SPENDING.format(
        extra_items=", line_total_lbp AS amount_lbp", extra_whole=f", {_LBP.format(amount='r.total')}",
        extra_rest=f", {_LBP.format(amount='(r.total - items.total)')}"))


def downgrade() -> None:
    # A view cannot lose a column in place, so the three views are rebuilt as 0007 left them.
    op.execute("DROP VIEW assistant.category_spending")
    op.execute("DROP VIEW assistant.purchases")
    op.execute("DROP VIEW assistant.receipts")
    op.execute("CREATE VIEW assistant.receipts AS " + _RECEIPTS.format(extra=""))
    op.execute("CREATE VIEW assistant.purchases AS " + _PURCHASES.format(extra=""))
    op.execute("CREATE VIEW assistant.category_spending AS "
               + _CATEGORY_SPENDING.format(extra_items="", extra_whole="", extra_rest=""))
    op.execute("GRANT SELECT ON assistant.receipts, assistant.purchases, assistant.category_spending TO ai_readonly")
