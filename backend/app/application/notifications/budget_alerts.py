from app.application.budgets.budget_status import BudgetStatusCalculator
from app.application.shared.unit_of_work import UnitOfWork
from app.domain.notifications.notification import BudgetSnapshot, budget_notification


class BudgetAlerts:
    """Checks this month's budgets and records any budget notification that is due.

    Called inside the same unit of work as the change that may have moved a budget (a confirmed,
    corrected or deleted receipt, or a budget being set), so the notification is saved together with
    the change or not at all. Notifications already sent are skipped by their dedup key.
    """

    def __init__(self, calculator: BudgetStatusCalculator) -> None:
        self._calculator = calculator

    def check(self, work: UnitOfWork) -> None:
        for status in self._calculator.statuses(work, self._calculator.current_month()):
            notification = budget_notification(
                BudgetSnapshot(
                    category_id=status.category_id,
                    category_name=status.category_name,
                    month=status.month,
                    currency=status.currency,
                    limit_amount=status.limit_amount,
                    spent=status.spent,
                    percent_used=status.percent_used,
                    state=status.state,
                    projected=status.pace.projected if status.pace else None,
                    pace_low_confidence=status.pace.low_confidence if status.pace else True,
                )
            )
            if notification is not None:
                work.notifications.add(notification)
