"""HTTP shapes for budgets. Amounts are Decimal, sent as JSON strings to stay exact."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.application.budgets.dtos import BudgetStatus

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class BudgetIn(BaseModel):
    month: str = Field(pattern=MONTH_PATTERN, examples=["2026-10"])  # applies from this month onwards
    currency: Literal["USD", "LBP"] = "USD"
    limit_amount: Decimal


class PaceOut(BaseModel):
    projected: Decimal
    low_confidence: bool
    projected_over: bool


class BudgetStatusOut(BaseModel):
    category_id: int
    category_name: str
    month: date
    set_in: date
    currency: str
    limit_amount: Decimal
    spent: Decimal
    remaining: Decimal
    percent_used: Decimal
    state: str
    pace: PaceOut | None

    @classmethod
    def from_status(cls, status: BudgetStatus) -> "BudgetStatusOut":
        return cls(
            category_id=status.category_id,
            category_name=status.category_name,
            month=status.month,
            set_in=status.set_in,
            currency=status.currency.value,
            limit_amount=status.limit_amount,
            spent=status.spent,
            remaining=status.remaining,
            percent_used=status.percent_used,
            state=status.state.value,
            pace=PaceOut(**vars(status.pace)) if status.pace else None,
        )
