from dataclasses import dataclass

from app.application.auth.auth_service import AuthService
from app.application.categories.category_service import CategoryService
from app.application.receipts.receipt_service import ReceiptService


@dataclass(frozen=True)
class Container:
    """The services the routers call, one per feature. Built in `app.main`; tests build their own."""

    auth: AuthService
    receipts: ReceiptService
    categories: CategoryService
