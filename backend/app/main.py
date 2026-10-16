"""Composition root: the only place that knows every layer and wires them together.

Run with:  uvicorn app.main:app --reload
"""

import logging
from collections.abc import Callable
from datetime import date

from fastapi import FastAPI

from app.api.app import create_app
from app.api.container import Container
from app.application.assistant.assistant_service import AssistantService
from app.application.auth.auth_service import AuthService
from app.application.budgets.budget_service import BudgetService
from app.application.budgets.budget_status import BudgetStatusCalculator
from app.application.categories.category_service import CategoryService
from app.application.notifications.budget_alerts import BudgetAlerts
from app.application.notifications.notification_service import NotificationService
from app.application.receipts.interfaces import FileStorage, ReceiptExtractor
from app.application.receipts.receipt_service import ReceiptService
from app.application.spending.spending_service import SpendingService
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import create_db_engine
from app.infrastructure.database.readonly_query_runner import SqlReadOnlyQueryRunner, UnavailableQueryRunner
from app.infrastructure.database.unit_of_work import SqlUnitOfWorkFactory
from app.infrastructure.database.user_repository import SqlUserRepository
from app.infrastructure.extraction.gemini_receipt_extractor import GeminiReceiptExtractor
from app.infrastructure.extraction.unavailable_receipt_extractor import UnavailableReceiptExtractor
from app.infrastructure.security.password_hasher import Argon2PasswordHasher
from app.infrastructure.security.token_service import JwtTokenService
from app.infrastructure.sql.sql_guard import SqlGlotGuard
from app.infrastructure.storage.local_file_storage import LocalFileStorage


def build_container(
    settings: Settings,
    extractor: ReceiptExtractor | None = None,
    storage: FileStorage | None = None,
    today: Callable[[], date] = date.today,
) -> Container:
    """Wire the real implementations. Tests pass their own extractor, storage and today's date."""
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set (see backend/.env.example)")

    engine = create_db_engine(settings.database_url)
    uow = SqlUnitOfWorkFactory(engine)
    storage = storage or LocalFileStorage(settings.upload_dir)
    if extractor is None:
        extractor = (
            GeminiReceiptExtractor(settings.gemini_api_key, [settings.gemini_model, settings.gemini_fallback_model])
            if settings.gemini_api_key
            else UnavailableReceiptExtractor()
        )

    budget_status = BudgetStatusCalculator(settings.default_lbp_per_usd, today)
    # Generated SQL runs through its own read-only role (ai_readonly), never the app's connection.
    query_runner = (
        SqlReadOnlyQueryRunner(create_db_engine(settings.readonly_database_url))
        if settings.readonly_database_url
        else UnavailableQueryRunner()
    )
    alerts = BudgetAlerts(budget_status)

    return Container(
        auth=AuthService(
            users=SqlUserRepository(engine),
            hasher=Argon2PasswordHasher(),
            tokens=JwtTokenService(settings.jwt_secret, settings.jwt_expire_minutes),
        ),
        receipts=ReceiptService(uow, storage, extractor, settings.default_lbp_per_usd, alerts, today),
        categories=CategoryService(uow),
        spending=SpendingService(uow, settings.default_lbp_per_usd),
        budgets=BudgetService(uow, budget_status, alerts),
        notifications=NotificationService(uow),
        assistant=AssistantService(uow, SqlGlotGuard(), query_runner),
    )


def build_app(settings: Settings | None = None) -> FastAPI:
    # Show the app's own log messages (e.g. why a receipt could not be read) next to uvicorn's.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return create_app(build_container(settings or Settings()))


app = build_app()
