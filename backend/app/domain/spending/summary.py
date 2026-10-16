"""How spending is added up (scope section 6.4, plus the decisions agreed on 2026-10-14).

- Only confirmed receipts count, in the month of the date printed on them.
- Overall spending is the sum of receipt totals.
- Category spending uses line totals. A line without a category takes its receipt's category, and only
  when both are missing does it count as Uncategorized.
- A receipt with no lines counts its whole total under its receipt category (or Uncategorized).
- Per receipt, `total - sum of line totals` is "Tax, discounts & rounding". It can be negative (discounts)
  and is never assigned to a category, so categories plus this entry always add up to the overall total.
- Currencies are never mixed inside a breakdown. A combined view first converts every receipt into one
  currency, each at its own saved rate.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.receipts.categorization import CategoryId, effective_category
from app.domain.receipts.receipt import Receipt
from app.domain.shared.currency import Currency
from app.domain.shared.exchange_rate import convert
from app.domain.spending.errors import InvalidMonth

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Breakdown:
    currency: Currency
    total: Decimal
    by_category: dict[CategoryId, Decimal]  # the key None means Uncategorized
    adjustments: Decimal  # "Tax, discounts & rounding"; may be negative
    receipt_count: int


# Years the app accepts. 0000-01 is not a real date and 9999-12 has no "next month" to end at,
# so both used to crash instead of being refused (2026-10-15 code review).
MIN_YEAR, MAX_YEAR = 1900, 9998


def month_range(year: int, month: int) -> tuple[date, date]:
    """The first day of the month and the first day of the next one (end is exclusive)."""
    if not (MIN_YEAR <= year <= MAX_YEAR and 1 <= month <= 12):
        raise InvalidMonth
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def breakdown(receipts: Sequence[Receipt], currency: Currency) -> Breakdown:
    """Spending in one currency. Receipts in other currencies, or without a total, are ignored."""
    total = Decimal(0)
    adjustments = Decimal(0)
    by_category: dict[CategoryId, Decimal] = defaultdict(Decimal)
    count = 0
    for receipt in receipts:
        if receipt.currency is not currency or receipt.total is None:
            continue
        count += 1
        total += receipt.total
        if receipt.lines:
            for line in receipt.lines:
                by_category[effective_category(line.category_id, receipt.primary_category_id)] += line.line_total
            adjustments += receipt.total - receipt.lines_total
        else:
            by_category[receipt.primary_category_id] += receipt.total
    return Breakdown(currency, total, dict(by_category), adjustments, count)


def convert_receipt(receipt: Receipt, to_currency: Currency, fallback_lbp_per_usd: Decimal) -> Receipt:
    """The same receipt with every amount in `to_currency`, at the receipt's own saved rate.
    The fallback (today's rate) is only used for a receipt that has no saved rate."""
    if receipt.currency is None or receipt.total is None or receipt.currency is to_currency:
        return receipt
    rate = receipt.lbp_per_usd if receipt.lbp_per_usd is not None else fallback_lbp_per_usd

    def to(amount: Decimal) -> Decimal:
        return convert(amount, receipt.currency, to_currency, rate)

    return replace(
        receipt,
        currency=to_currency,
        total=to(receipt.total),
        lines=tuple(replace(line, line_total=to(line.line_total)) for line in receipt.lines),
    )


def combined_breakdown(
    receipts: Sequence[Receipt], currency: Currency, fallback_lbp_per_usd: Decimal
) -> Breakdown:
    """All receipts in one currency, for the single total the user sees."""
    return breakdown([convert_receipt(r, currency, fallback_lbp_per_usd) for r in receipts], currency)


def rounded(result: Breakdown) -> Breakdown:
    """Round for display. Categories and the total are rounded to cents, and the adjustment is
    worked out from them, so the shown numbers still add up exactly (it absorbs rounding cents)."""
    total = result.total.quantize(CENT, ROUND_HALF_UP)
    by_category = {key: amount.quantize(CENT, ROUND_HALF_UP) for key, amount in result.by_category.items()}
    adjustments = total - sum(by_category.values(), Decimal(0))
    return replace(result, total=total, by_category=by_category, adjustments=adjustments)
