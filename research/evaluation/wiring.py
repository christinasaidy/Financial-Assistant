"""The evaluation's own composition root: it wires the app's public parts the way the evaluation needs them.

It never uses app.main (that builds the web app). The assistant is the app's own AssistantService, with the app's
guard, answering rules and read-only runner, so the evaluation scores exactly the SQL step the app runs. Only the
model, the date and the receipt reader differ.
"""

import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import app
from app.application.assistant.assistant_service import AssistantService
from app.application.assistant.interfaces import AssistantModel
from app.application.auth.auth_service import AuthService
from app.application.budgets.budget_status import BudgetStatusCalculator
from app.application.categories.category_service import CategoryService
from app.application.notifications.budget_alerts import BudgetAlerts
from app.application.receipts.receipt_service import ReceiptService
from app.domain.receipts.errors import ExtractionFailed
from app.domain.receipts.extraction import ExtractedReceipt
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import create_db_engine
from app.infrastructure.database.readonly_query_runner import SqlReadOnlyQueryRunner
from app.infrastructure.database.unit_of_work import SqlUnitOfWorkFactory
from app.infrastructure.database.user_repository import SqlUserRepository
from app.infrastructure.security.password_hasher import Argon2PasswordHasher
from app.infrastructure.security.token_service import JwtTokenService
from app.infrastructure.sql.query_rules import SqlGlotQueryRules
from app.infrastructure.sql.sql_guard import SqlGlotGuard
from app.infrastructure.storage.local_file_storage import LocalFileStorage

BACKEND_DIR = Path(app.__file__).resolve().parents[1]


def load_settings() -> Settings:
    """The backend's settings, from backend/.env wherever the evaluation is started."""
    return Settings(_env_file=BACKEND_DIR / ".env")


class SeedReceiptReader:
    """Stands in for the vision model when the seed adds a receipt that waits for review: it returns the receipt it
    was given. No model is called."""

    def __init__(self) -> None:
        self.next: ExtractedReceipt | None = None

    def extract(
        self, content: bytes, content_type: str, category_names: Sequence[str], known_names: Sequence[str] = ()
    ) -> ExtractedReceipt:
        if self.next is None:
            raise ExtractionFailed("No receipt was prepared")
        return self.next


@dataclass(frozen=True)
class Evaluation:
    assistant: AssistantService
    receipts: ReceiptService
    categories: CategoryService
    auth: AuthService
    reader: SeedReceiptReader
    settings: Settings


def build_evaluation(settings: Settings, model: AssistantModel, today: date, storage_dir: Path) -> Evaluation:
    if not settings.readonly_database_url:
        raise RuntimeError("READONLY_DATABASE_URL is not set: the evaluation runs queries as the read-only role")
    engine = create_db_engine(settings.database_url)
    uow = SqlUnitOfWorkFactory(engine)
    on_day = lambda: today  # noqa: E731
    reader = SeedReceiptReader()
    alerts = BudgetAlerts(BudgetStatusCalculator(settings.default_lbp_per_usd, on_day))
    return Evaluation(
        assistant=AssistantService(
            uow, SqlGlotGuard(), SqlReadOnlyQueryRunner(create_db_engine(settings.readonly_database_url)),
            SqlGlotQueryRules(), model, on_day,
        ),  # fmt: skip
        receipts=ReceiptService(uow, LocalFileStorage(storage_dir), reader, settings.default_lbp_per_usd, alerts,
                                on_day),  # fmt: skip
        categories=CategoryService(uow),
        # Only `register` is used; no token is ever issued, so a throwaway signing key is enough.
        auth=AuthService(SqlUserRepository(engine), Argon2PasswordHasher(), JwtTokenService(secrets.token_urlsafe(48))),
        reader=reader,
        settings=settings,
    )
