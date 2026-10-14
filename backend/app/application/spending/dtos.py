from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.shared.currency import Currency


@dataclass(frozen=True)
class CategoryAmount:
    category_id: int | None  # None means Uncategorized
    name: str
    amount: Decimal


@dataclass(frozen=True)
class CurrencySummary:
    currency: Currency
    total: Decimal
    categories: list[CategoryAmount]  # largest first
    adjustments: Decimal  # "Tax, discounts & rounding"; may be negative
    receipt_count: int


@dataclass(frozen=True)
class MonthlySummary:
    month: date  # the first day of the month
    combined: CurrencySummary  # everything converted into the currency the user chose
    by_currency: list[CurrencySummary]  # the exact amounts, one entry per currency actually used
    awaiting_review: int  # receipts read but not confirmed yet; not counted in any total
    converted_at_current_rate: int  # receipts with no saved rate, converted at today's rate
    current_lbp_per_usd: Decimal
