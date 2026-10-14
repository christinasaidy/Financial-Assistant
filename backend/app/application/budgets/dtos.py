from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.budgets.budget import BudgetState
from app.domain.shared.currency import Currency


@dataclass(frozen=True)
class SetBudgetRequest:
    category_id: int
    year: int
    month: int  # the amount applies from this month onwards
    currency: Currency
    limit_amount: Decimal


@dataclass(frozen=True)
class Pace:
    projected: Decimal  # where spending ends up at this rate by the end of the month
    low_confidence: bool  # the first 7 days of the month
    projected_over: bool  # on pace to go past the limit


@dataclass(frozen=True)
class BudgetStatus:
    category_id: int
    category_name: str
    month: date  # the month being looked at
    set_in: date  # the month this amount was set (it repeats until changed)
    currency: Currency
    limit_amount: Decimal
    spent: Decimal  # category spending only; tax and discounts are not counted
    remaining: Decimal  # negative once the limit is passed
    percent_used: Decimal
    state: BudgetState
    pace: Pace | None  # only for the current month
