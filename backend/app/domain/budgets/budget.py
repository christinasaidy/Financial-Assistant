"""Monthly category budgets (decisions agreed with the user on 2026-10-14).

- A budget repeats: the amount set for a month applies to every later month until a new amount is set.
- One budget per category, in one currency. Spending in both currencies counts, each receipt converted at
  its own saved rate. Only category spending counts; "Tax, discounts & rounding" does not.
- States: ok below 80% of the limit, near from 80% up to 100%, limit_reached at 100% or more.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.domain.budgets.errors import InvalidBudget
from app.domain.receipts.receipt import MAX_AMOUNT
from app.domain.shared.currency import Currency

NEAR_THRESHOLD = Decimal("0.80")


class BudgetState(StrEnum):
    OK = "ok"
    NEAR = "near"
    LIMIT_REACHED = "limit_reached"


@dataclass(frozen=True)
class Budget:
    category_id: int
    month: date  # the first day of the month this amount was set for
    currency: Currency
    limit_amount: Decimal


def validate_limit(limit_amount: Decimal) -> None:
    if not 0 < limit_amount <= MAX_AMOUNT:
        raise InvalidBudget("The budget amount must be greater than zero")


def budget_state(spent: Decimal, limit_amount: Decimal) -> BudgetState:
    if spent >= limit_amount:
        return BudgetState.LIMIT_REACHED
    if spent >= limit_amount * NEAR_THRESHOLD:
        return BudgetState.NEAR
    return BudgetState.OK


def budgets_for_month(budgets: Sequence[Budget], month: date) -> dict[int, Budget]:
    """The budget that applies to `month` for each category: the latest one set on or before it."""
    applying: dict[int, Budget] = {}
    for budget in budgets:
        if budget.month > month:
            continue
        current = applying.get(budget.category_id)
        if current is None or budget.month > current.month:
            applying[budget.category_id] = budget
    return applying
