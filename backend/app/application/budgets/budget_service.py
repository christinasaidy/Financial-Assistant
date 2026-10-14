import calendar
from collections.abc import Callable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.application.budgets.dtos import BudgetStatus, Pace, SetBudgetRequest
from app.application.shared.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.domain.budgets.budget import Budget, budget_state, budgets_for_month, validate_limit
from app.domain.budgets.errors import BudgetNotFound, InvalidBudget
from app.domain.budgets.pace import project_month_end
from app.domain.spending.summary import CENT, combined_breakdown, month_range

ONE_DECIMAL = Decimal("0.1")


class BudgetService:
    """Monthly category budgets, how much of each is used, and the pace for the current month."""

    def __init__(
        self,
        uow: UnitOfWorkFactory,
        default_lbp_per_usd: Decimal,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._uow = uow
        self._default_lbp_per_usd = default_lbp_per_usd  # only for receipts that have no saved rate
        self._today = today

    def set_budget(self, user_id: int, request: SetBudgetRequest) -> BudgetStatus:
        """Set a category's budget from `month` onwards. Earlier months keep their amount."""
        validate_limit(request.limit_amount)
        month, _ = month_range(request.year, request.month)
        with self._uow(user_id) as work:
            if request.category_id not in {category.id for category in work.categories.list_all()}:
                raise InvalidBudget("Unknown category")
            work.budgets.set(request.category_id, month, request.currency, request.limit_amount)
            statuses = self._statuses(work, month)
        return next(status for status in statuses if status.category_id == request.category_id)

    def list_for_month(self, user_id: int, year: int, month: int) -> list[BudgetStatus]:
        """Every budget that applies to the month, with how much of it is used."""
        start, _ = month_range(year, month)
        with self._uow(user_id) as work:
            return self._statuses(work, start)

    def delete_budget(self, user_id: int, category_id: int) -> None:
        """Remove the category's budget completely, for every month."""
        with self._uow(user_id) as work:
            if work.budgets.delete_category(category_id) == 0:
                raise BudgetNotFound

    def _statuses(self, work: UnitOfWork, month: date) -> list[BudgetStatus]:
        applying = budgets_for_month(work.budgets.list_up_to(month), month)
        if not applying:
            return []
        start, end = month_range(month.year, month.month)
        receipts = work.receipts.list_confirmed_between(start, end)
        names = {category.id: category.name for category in work.categories.list_all()}

        # Category spending (tax and discounts excluded) in each currency a budget is set in.
        spent_by_currency = {
            currency: combined_breakdown(receipts, currency, self._default_lbp_per_usd).by_category
            for currency in {budget.currency for budget in applying.values()}
        }
        statuses = [
            self._status(budget, month, names.get(budget.category_id, ""), spent_by_currency[budget.currency])
            for budget in applying.values()
        ]
        return sorted(statuses, key=lambda status: status.category_name)

    def _status(self, budget: Budget, month: date, name: str, spent_by_category: dict) -> BudgetStatus:
        spent = spent_by_category.get(budget.category_id, Decimal(0)).quantize(CENT, ROUND_HALF_UP)
        return BudgetStatus(
            category_id=budget.category_id,
            category_name=name,
            month=month,
            set_in=budget.month,
            currency=budget.currency,
            limit_amount=budget.limit_amount,
            spent=spent,
            remaining=budget.limit_amount - spent,
            percent_used=(spent / budget.limit_amount * 100).quantize(ONE_DECIMAL, ROUND_HALF_UP),
            state=budget_state(spent, budget.limit_amount),
            pace=self._pace(month, spent, budget.limit_amount),
        )

    def _pace(self, month: date, spent: Decimal, limit_amount: Decimal) -> Pace | None:
        today = self._today()
        if (today.year, today.month) != (month.year, month.month):
            return None  # past months show what was spent; future months have nothing to project
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        projection = project_month_end(spent, today.day, days_in_month)
        projected = projection.projected.quantize(CENT, ROUND_HALF_UP)
        return Pace(
            projected=projected, low_confidence=projection.low_confidence, projected_over=projected > limit_amount
        )
