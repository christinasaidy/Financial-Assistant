from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine

from app.infrastructure.database.budget_repository import SqlBudgetRepository
from app.infrastructure.database.category_repository import SqlCategoryRepository
from app.infrastructure.database.connection import user_scoped_connection
from app.infrastructure.database.notification_repository import SqlNotificationRepository
from app.infrastructure.database.receipt_repository import SqlReceiptRepository
from app.infrastructure.database.vendor_repository import SqlVendorRepository


class SqlUnitOfWork:
    """Repositories that all share one connection, and so one transaction and one user."""

    def __init__(self, conn: Connection) -> None:
        self.receipts = SqlReceiptRepository(conn)
        self.vendors = SqlVendorRepository(conn)
        self.categories = SqlCategoryRepository(conn)
        self.budgets = SqlBudgetRepository(conn)
        self.notifications = SqlNotificationRepository(conn)


class SqlUnitOfWorkFactory:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def __call__(self, user_id: int) -> Iterator[SqlUnitOfWork]:
        # Commits on a normal exit and rolls back on any exception. This is the only place a
        # user-data transaction is opened, so `app.user_id` is always set for these repositories.
        with user_scoped_connection(self._engine, user_id) as conn:
            yield SqlUnitOfWork(conn)
