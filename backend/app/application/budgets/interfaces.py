from datetime import date
from decimal import Decimal
from typing import Protocol

from app.domain.budgets.budget import Budget
from app.domain.shared.currency import Currency


class BudgetRepository(Protocol):
    def list_up_to(self, month: date) -> list[Budget]:
        """Every budget amount set for `month` or any earlier month."""

    def set(self, category_id: int, month: date, currency: Currency, limit_amount: Decimal) -> None:
        """Create or replace the amount set for this category and month."""

    def delete_category(self, category_id: int) -> int:
        """Remove the category's budget for every month. Returns how many amounts were removed."""
