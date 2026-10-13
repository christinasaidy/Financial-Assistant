from dataclasses import dataclass

from app.application.auth.get_current_user import GetCurrentUser
from app.application.auth.login import Login
from app.application.auth.ports import TokenService
from app.application.auth.register_user import RegisterUser
from app.application.categories.list_categories import ListCategories
from app.application.receipts.confirm_receipt import ConfirmReceipt
from app.application.receipts.create_manual_receipt import CreateManualReceipt
from app.application.receipts.delete_receipt import DeleteReceipt
from app.application.receipts.get_receipt import GetReceipt
from app.application.receipts.list_receipts import ListReceipts
from app.application.receipts.process_receipt import ProcessReceipt
from app.application.receipts.upload_receipt import UploadReceipt


@dataclass(frozen=True)
class AuthServices:
    register_user: RegisterUser
    login: Login
    get_current_user: GetCurrentUser
    tokens: TokenService


@dataclass(frozen=True)
class ReceiptServices:
    upload: UploadReceipt
    process: ProcessReceipt
    confirm: ConfirmReceipt
    create_manual: CreateManualReceipt
    get: GetReceipt
    list_all: ListReceipts
    delete: DeleteReceipt


@dataclass(frozen=True)
class CategoryServices:
    list_all: ListCategories


@dataclass(frozen=True)
class Container:
    """Everything the routers need, already wired and grouped by feature.
    Built in `app.main`; tests build their own."""

    auth: AuthServices
    receipts: ReceiptServices
    categories: CategoryServices
