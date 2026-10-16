from app.application.budgets.budget_status import BudgetStatusCalculator
from app.application.budgets.dtos import BudgetStatus, SetBudgetRequest
from app.application.notifications.budget_alerts import BudgetAlerts
from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.domain.budgets.budget import validate_limit
from app.domain.budgets.errors import BudgetNotFound, InvalidBudget
from app.domain.spending.summary import month_range


class BudgetService:
    """Monthly category budgets, how much of each is used, and the pace for the current month."""

    def __init__(self, uow: UnitOfWorkFactory, calculator: BudgetStatusCalculator, alerts: BudgetAlerts) -> None:
        self._uow = uow
        self._calculator = calculator
        self._alerts = alerts

    def set_budget(self, user_id: int, request: SetBudgetRequest) -> BudgetStatus:
        """Set a category's budget from `month` onwards. Earlier months keep their amount."""
        validate_limit(request.limit_amount)
        month, _ = month_range(request.year, request.month)
        with self._uow(user_id, serialized=True) as work:  # checks budget alerts: see UnitOfWorkFactory
            if request.category_id not in {category.id for category in work.categories.list_all()}:
                raise InvalidBudget("Unknown category")
            work.budgets.set(request.category_id, month, request.currency, request.limit_amount)
            self._alerts.check(work)  # e.g. a budget lowered below what is already spent
            statuses = self._calculator.statuses(work, month)
        return next(status for status in statuses if status.category_id == request.category_id)

    def list_for_month(self, user_id: int, year: int, month: int) -> list[BudgetStatus]:
        """Every budget that applies to the month, with how much of it is used."""
        start, _ = month_range(year, month)
        with self._uow(user_id) as work:
            return self._calculator.statuses(work, start)

    def delete_budget(self, user_id: int, category_id: int) -> None:
        """Remove the category's budget completely, for every month."""
        with self._uow(user_id) as work:
            if work.budgets.delete_category(category_id) == 0:
                raise BudgetNotFound
