"""HTTP shapes for spending. Amounts are Decimal, sent as JSON strings to stay exact."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.application.spending.dtos import CurrencySummary, MonthlySummary


class CategoryAmountOut(BaseModel):
    category_id: int | None
    name: str
    amount: Decimal


class CurrencySummaryOut(BaseModel):
    currency: str
    total: Decimal
    categories: list[CategoryAmountOut]
    adjustments: Decimal
    receipt_count: int

    @classmethod
    def from_summary(cls, summary: CurrencySummary) -> "CurrencySummaryOut":
        return cls(
            currency=summary.currency.value,
            total=summary.total,
            categories=[CategoryAmountOut(**vars(item)) for item in summary.categories],
            adjustments=summary.adjustments,
            receipt_count=summary.receipt_count,
        )


class MonthlySummaryOut(BaseModel):
    month: date
    combined: CurrencySummaryOut
    by_currency: list[CurrencySummaryOut]
    awaiting_review: int
    converted_at_current_rate: int
    current_lbp_per_usd: Decimal

    @classmethod
    def from_summary(cls, summary: MonthlySummary) -> "MonthlySummaryOut":
        return cls(
            month=summary.month,
            combined=CurrencySummaryOut.from_summary(summary.combined),
            by_currency=[CurrencySummaryOut.from_summary(item) for item in summary.by_currency],
            awaiting_review=summary.awaiting_review,
            converted_at_current_rate=summary.converted_at_current_rate,
            current_lbp_per_usd=summary.current_lbp_per_usd,
        )
