"""Composition root: the only place that knows every layer and wires them together.

Run with:  uvicorn app.main:app --reload
"""

import logging
from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from app.api.app import create_app
from app.api.container import Container
from app.application.assistant.assistant_service import AssistantService
from app.application.assistant.interfaces import AssistantModel, StandardAssistant, StandardChatModel
from app.application.assistant.memory_service import MemoryService
from app.application.assistant.standard_skills import BUDGETS, PRICE_COMPARISONS
from app.application.assistant.standard_tools import StandardTools
from app.application.assistant.standard_workflow import StandardLimits, StandardWorkflow
from app.domain.assistant.usage import Pricing, StandardQuota
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
from app.infrastructure.language_model.anthropic_chat_model import AnthropicChatModel
from app.infrastructure.language_model.openai_compatible_assistant_model import OpenAiCompatibleAssistantModel
from app.infrastructure.language_model.unavailable_assistant_model import UnavailableAssistantModel
from app.infrastructure.security.password_hasher import Argon2PasswordHasher
from app.infrastructure.skills.arabizi_pack import ArabiziPackUnavailable, load_arabizi_pack
from app.infrastructure.security.token_service import JwtTokenService
from app.infrastructure.sql.query_rules import SqlGlotQueryRules
from app.infrastructure.sql.sql_guard import SqlGlotGuard
from app.infrastructure.storage.local_file_storage import LocalFileStorage

logger = logging.getLogger(__name__)


def build_container(
    settings: Settings,
    extractor: ReceiptExtractor | None = None,
    storage: FileStorage | None = None,
    today: Callable[[], date] | None = None,
    assistant_model: AssistantModel | None = None,
    standard_assistant: StandardAssistant | None = None,
    standard_model: StandardChatModel | None = None,
) -> Container:
    """Wire the real implementations. Tests pass their own extractor, storage, language models and today's date:
    `standard_assistant` replaces the whole Standard workflow, `standard_model` only its model (the real workflow
    and tools then run around it).

    The two assistant modes are wired independently: a missing Beta model or a missing Standard key leaves only
    that mode unavailable, and the rest of the app works either way."""
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

    if assistant_model is None:
        api_key = settings.assistant_api_key or settings.gemini_api_key
        assistant_model = (
            OpenAiCompatibleAssistantModel(
                settings.assistant_base_url,
                api_key,
                settings.assistant_sql_model,
                settings.assistant_answer_model,
                timeout=settings.assistant_timeout_seconds,
                thinking=settings.assistant_thinking,
            )
            if api_key
            else UnavailableAssistantModel()
        )
    beta_available = not isinstance(assistant_model, UnavailableAssistantModel)
    # The assistant's "today" is Beirut's date (the server's clock may be elsewhere); a test's date wins.
    time_zone = ZoneInfo(settings.assistant_time_zone)
    assistant_today = today or (lambda: datetime.now(time_zone).date())
    today = today or date.today

    budget_status = BudgetStatusCalculator(settings.default_lbp_per_usd, today)
    # Generated SQL runs through its own read-only role (ai_readonly), never the app's connection.
    query_runner = (
        SqlReadOnlyQueryRunner(create_db_engine(settings.readonly_database_url))
        if settings.readonly_database_url
        else UnavailableQueryRunner()
    )
    alerts = BudgetAlerts(budget_status)
    receipts = ReceiptService(uow, storage, extractor, settings.default_lbp_per_usd, alerts, today)
    spending = SpendingService(uow, settings.default_lbp_per_usd)
    budgets = BudgetService(uow, budget_status, alerts)
    guard, rules = SqlGlotGuard(), SqlGlotQueryRules()

    # Standard: only when switched on with a key and a model (no paid call is ever made by accident). Its tools use
    # the same services, guard, rules and read-only role as the rest of the app.
    memories = MemoryService(uow)
    closers: list[Callable[[], None]] = []
    wanted = standard_assistant is None and (standard_model is not None or settings.standard_assistant_configured)
    # Standard never runs without the owner's Arabizi rulings: a missing, edited or unreviewed pack leaves it
    # unavailable (handoff section 13A), and the reason is logged.
    pack = None
    if wanted:
        try:
            pack = load_arabizi_pack()
        except ArabiziPackUnavailable as exc:
            logger.error("The Standard assistant is unavailable: %s", exc)
    if wanted and pack is not None and standard_model is None:
        chat = AnthropicChatModel(
            settings.anthropic_api_key,
            settings.standard_assistant_model,
            max_output_tokens=settings.standard_assistant_max_output_tokens,
            effort=settings.standard_assistant_effort,
            timeout=settings.standard_assistant_timeout_seconds,
            max_retries=settings.standard_assistant_max_retries,
            cache_ttl=settings.standard_assistant_cache_ttl,
        )
        closers.append(chat.close)
        standard_model = chat
    if wanted and pack is not None:
        tools = StandardTools(uow, guard, rules, query_runner, spending, budgets, receipts, memories=memories)
        limits = StandardLimits(
            max_tool_rounds=settings.standard_assistant_max_tool_rounds,
            max_tool_calls=settings.standard_assistant_max_tool_calls,
            deadline_seconds=settings.standard_assistant_deadline_seconds,
        )
        standard_assistant = StandardWorkflow(standard_model, tools, assistant_today, limits,
                                              skills=(PRICE_COMPARISONS, BUDGETS, pack.skill),
                                              arabizi_words=pack.words, pricing=_pricing(settings))  # fmt: skip

    return Container(
        auth=AuthService(
            users=SqlUserRepository(engine),
            hasher=Argon2PasswordHasher(),
            tokens=JwtTokenService(settings.jwt_secret, settings.jwt_expire_minutes),
            files=storage,
        ),
        receipts=receipts,
        categories=CategoryService(uow),
        spending=spending,
        budgets=budgets,
        notifications=NotificationService(uow),
        memories=memories,
        assistant=AssistantService(
            uow,
            guard,
            query_runner,
            rules,
            assistant_model,
            assistant_today,
            settings.assistant_history_exchanges,
            settings.assistant_history_characters,
            standard=standard_assistant,
            beta_available=beta_available,
            turn_timeout_seconds=settings.assistant_turn_timeout_seconds,
            standard_quota=StandardQuota(
                settings.standard_assistant_daily_questions_per_user or None,
                settings.standard_assistant_monthly_cap_dollars,
                settings.standard_assistant_question_reserve_dollars,
                settings.assistant_time_zone,
            ),
        ),
        closers=tuple(closers),
    )


def _pricing(settings: Settings) -> Pricing | None:
    """The configured Standard prices, or None (no estimates) if any is missing."""
    prices = (settings.standard_price_input_per_mtok, settings.standard_price_output_per_mtok,
              settings.standard_price_cache_write_5m_per_mtok, settings.standard_price_cache_write_1h_per_mtok,
              settings.standard_price_cache_read_per_mtok)  # fmt: skip
    if any(price is None for price in prices):
        return None
    return Pricing(settings.standard_pricing_version, *prices)


def build_app(settings: Settings | None = None) -> FastAPI:
    # Show the app's own log messages (e.g. why a receipt could not be read) next to uvicorn's.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return create_app(build_container(settings or Settings()))


app = build_app()
