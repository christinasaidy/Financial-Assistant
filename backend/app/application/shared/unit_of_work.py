"""One database transaction for one user.

Every repository a service method touches comes from the same unit of work, so the changes are saved
together or not at all, and all of them run as the given user (row-level security).
"""

from contextlib import AbstractContextManager
from typing import Protocol

from app.application.assistant.interfaces import ConversationRepository, FeedbackRepository, MessageRepository
from app.application.budgets.interfaces import BudgetRepository
from app.application.categories.interfaces import CategoryRepository
from app.application.notifications.interfaces import NotificationRepository
from app.application.receipts.interfaces import ReceiptRepository, VendorRepository


class UnitOfWork(Protocol):
    receipts: ReceiptRepository
    vendors: VendorRepository
    categories: CategoryRepository
    budgets: BudgetRepository
    notifications: NotificationRepository
    conversations: ConversationRepository
    messages: MessageRepository
    feedback: FeedbackRepository


class UnitOfWorkFactory(Protocol):
    def __call__(self, user_id: int, serialized: bool = False) -> AbstractContextManager[UnitOfWork]:
        """Commits when the block ends normally, rolls everything back if it raises.

        `serialized=True` first waits until the user's other serialized units of work have finished, and holds
        them off until this one ends. Use it for every change that can move a budget (and so checks budget
        alerts): two such changes at once would each check the budget without the other's change and could both
        miss an alert (second code review, 2026-10-16). Reads and other changes do not need it."""
