from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.assistant.errors import (
    CannotRateQuestion,
    ConversationNotFound,
    InvalidQuestion,
    MessageNotFound,
    QueryFailed,
    UnsafeQuery,
)
from app.domain.budgets.errors import BudgetNotFound, InvalidBudget
from app.domain.notifications.errors import NotificationNotFound
from app.domain.receipts.errors import (
    DuplicateReceipt,
    FileTooLarge,
    InvalidReceipt,
    InvalidStateTransition,
    ReceiptNotFound,
    UnsupportedFileType,
)
from app.domain.shared.errors import DomainError
from app.domain.shared.exchange_rate import InvalidExchangeRate
from app.domain.spending.errors import InvalidMonth
from app.domain.users.errors import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidEmail,
    InvalidToken,
    WeakPassword,
)

# Domain error -> HTTP status. Controllers never contain business rules, only this translation.
# Matched with isinstance, so a subclass gets its parent's status. Anything unlisted is a 400.
_ERROR_STATUS: list[tuple[type[DomainError], int]] = [
    (InvalidCredentials, status.HTTP_401_UNAUTHORIZED),
    (InvalidToken, status.HTTP_401_UNAUTHORIZED),
    (ReceiptNotFound, status.HTTP_404_NOT_FOUND),
    (BudgetNotFound, status.HTTP_404_NOT_FOUND),
    (NotificationNotFound, status.HTTP_404_NOT_FOUND),
    (ConversationNotFound, status.HTTP_404_NOT_FOUND),
    (MessageNotFound, status.HTTP_404_NOT_FOUND),
    (EmailAlreadyRegistered, status.HTTP_409_CONFLICT),
    (DuplicateReceipt, status.HTTP_409_CONFLICT),
    (InvalidStateTransition, status.HTTP_409_CONFLICT),
    (FileTooLarge, 413),
    (UnsupportedFileType, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
    (InvalidEmail, 422),
    (WeakPassword, 422),
    (InvalidReceipt, 422),
    (InvalidExchangeRate, 422),
    (InvalidBudget, 422),
    (InvalidMonth, 422),
    (InvalidQuestion, 422),
    (CannotRateQuestion, 422),
    (UnsafeQuery, 422),
    (QueryFailed, 422),
]
_DEFAULT_STATUS = status.HTTP_400_BAD_REQUEST


def _handle(request: Request, exc: Exception) -> JSONResponse:
    code = next((code for error_type, code in _ERROR_STATUS if isinstance(exc, error_type)), _DEFAULT_STATUS)
    body: dict[str, object] = {"detail": str(exc) or "The request could not be completed"}
    if isinstance(exc, DuplicateReceipt):
        body["receipt_id"] = exc.existing_id
    headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, InvalidToken) else None
    return JSONResponse(body, status_code=code, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _handle)
