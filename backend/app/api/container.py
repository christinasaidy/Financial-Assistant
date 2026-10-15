from dataclasses import dataclass

from app.application.assistant.assistant_service import AssistantService
from app.application.auth.auth_service import AuthService
from app.application.budgets.budget_service import BudgetService
from app.application.categories.category_service import CategoryService
from app.application.notifications.notification_service import NotificationService
from app.application.receipts.receipt_service import ReceiptService
from app.application.spending.spending_service import SpendingService


@dataclass(frozen=True)
class Container:
    """The services the routers call, one per feature. Built in `app.main`; tests build their own."""

    auth: AuthService
    receipts: ReceiptService
    categories: CategoryService
    spending: SpendingService
    budgets: BudgetService
    notifications: NotificationService
    assistant: AssistantService
