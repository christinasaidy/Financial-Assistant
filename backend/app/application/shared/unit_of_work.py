"""One database transaction for one user.

Every repository a use case touches comes from the same unit of work, so the changes are saved
together or not at all, and all of them run as the given user (row-level security).
"""

from contextlib import AbstractContextManager
from typing import Protocol

from app.application.categories.ports import CategoryRepository
from app.application.receipts.ports import ReceiptRepository, VendorRepository


class UnitOfWork(Protocol):
    receipts: ReceiptRepository
    vendors: VendorRepository
    categories: CategoryRepository


class UnitOfWorkFactory(Protocol):
    def __call__(self, user_id: int) -> AbstractContextManager[UnitOfWork]:
        """Commits when the block ends normally, rolls everything back if it raises."""
