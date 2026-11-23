from decimal import Decimal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Runtime connection: the non-owner `app_user` role, so row-level security applies.
    database_url: str = "postgresql+psycopg://app_user:CHANGE_ME@localhost:5432/expense_tracker"
    # Used only by Alembic: the `expense_owner` role that owns the tables.
    migration_database_url: str | None = None
    # Used only to run AI-generated SQL: the read-only `ai_readonly` role.
    readonly_database_url: str | None = None

    # Signing key for access tokens (at least 32 characters). Required to run the API.
    jwt_secret: str | None = None
    jwt_expire_minutes: int = 60

    # Where uploaded receipt files are kept (relative to the folder the API runs from).
    upload_dir: str = "uploads"

    # Vision model for reading receipts. Without a key every upload ends as `failed`
    # and the user enters the receipt by hand.
    gemini_api_key: str | None = None
    # gemini-2.5-flash is closed to new API keys (checked 2026-10-15). 3.5-flash-lite read the sample receipts
    # correctly and answered reliably while the larger models were often overloaded.
    gemini_model: str = "gemini-3.5-flash-lite"
    # Optional second model, tried if the first keeps failing (e.g. "gemini-3.5-flash").
    gemini_fallback_model: str | None = None

    # The assistant's language model, through the OpenAI-compatible chat API (assistant phase 3). The defaults use
    # Gemini's OpenAI-compatible endpoint with GEMINI_API_KEY. For the fine-tuned model on RunPod, point the URL at
    # vLLM and set the SQL model to the LoRA adapter's name and the answer model to the base model's.
    # These settings are the Beta mode's (the SQL workflow; conversations from before the modes are Beta too).
    assistant_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    # Kept as it was: without it, GEMINI_API_KEY is used (the development setup). Never used for Standard.
    assistant_api_key: str | None = None
    assistant_sql_model: str = "gemini-3.5-flash-lite"
    assistant_answer_model: str = "gemini-3.5-flash-lite"
    # Whether the model may think before answering. Empty sends nothing (the model's own default; Gemini needs this);
    # false turns thinking off (Qwen3 on vLLM thinks by default, which is much slower), true turns it on.
    assistant_thinking: bool | None = None
    assistant_timeout_seconds: float = 60  # Gemini calls took 16-20 s in the live run of 2026-11-04
    # How much of the chat is sent with a question: whole exchanges, the oldest dropped first. Starting values,
    # not tested ones: tune them in the evaluation.
    assistant_history_exchanges: int = 6
    assistant_history_characters: int = 6000
    # "Today" for questions such as "this month", as a date in this time zone.
    assistant_time_zone: str = "Asia/Beirut"
    # A turn (answering one question) still running after this long is given up as abandoned, so the conversation
    # can be asked again after a crash or restart. Above Beta's worst case of four model calls of up to 2 x 60 s.
    assistant_turn_timeout_seconds: float = 900

    # The Standard mode: Anthropic's API with its own key. Off unless STANDARD_ASSISTANT_ENABLED is true AND a key
    # and a model are set, so no paid call is ever made by accident. Without it, Standard conversations are
    # answered "not available" and Beta is unaffected; neither mode ever falls back to the other.
    standard_assistant_enabled: bool = False
    anthropic_api_key: str | None = None
    standard_assistant_model: str | None = None  # claude-sonnet-5-5 (checked in Anthropic's model list 2026-11-23)
    # Limits approved by the owner on 2026-11-23. Output tokens include the model's thinking.
    standard_assistant_max_output_tokens: int = 2048
    standard_assistant_max_tool_rounds: int = 4
    standard_assistant_max_tool_calls: int = 8
    standard_assistant_timeout_seconds: float = 60  # each model call; the SDK retries it at most once more
    standard_assistant_max_retries: int = 1
    standard_assistant_deadline_seconds: float = 240  # no new model call starts after this much of a question
    standard_assistant_effort: str = "medium"  # low | medium | high | xhigh | max (the model's default is high)
    # How long the provider keeps the fixed instructions (with the Arabizi skill) cached: 5m or 1h (decided
    # 2026-11-23: every skill is always sent, so one 1-hour write serves every question while the app is in use).
    standard_assistant_cache_ttl: str = "1h"
    # Limits decided with the owner on 2026-11-23, in Beirut time (assistant_time_zone). Empty means no limit.
    standard_assistant_daily_questions_per_user: int | None = 30
    standard_assistant_monthly_cap_dollars: Decimal | None = Decimal("10")
    # What a question whose cost is not known yet counts as against the cap: about the most one can cost (6 model calls
    # of ~$0.045 at the limits above, plus one 1-hour cache write of the ~43,000-token instructions, ~$0.18).
    standard_assistant_question_reserve_dollars: Decimal = Decimal("0.50")
    # Prices for the cost estimates, in dollars per million tokens: Anthropic's list prices for claude-sonnet-5-5 on
    # https://platform.claude.com/docs/en/build-with-claude/prompt-caching (checked 2026-11-23). Change the version
    # with the prices; every estimate keeps the version it was made with. Any empty price: no estimate (unknown).
    standard_pricing_version: str = "anthropic-claude-sonnet-5-5-2026-11-23"
    standard_price_input_per_mtok: Decimal | None = Decimal("2.00")
    standard_price_output_per_mtok: Decimal | None = Decimal("10.00")
    standard_price_cache_write_5m_per_mtok: Decimal | None = Decimal("2.50")
    standard_price_cache_write_1h_per_mtok: Decimal | None = Decimal("4.00")
    standard_price_cache_read_per_mtok: Decimal | None = Decimal("0.10")

    @property
    def standard_assistant_configured(self) -> bool:
        return bool(self.standard_assistant_enabled and self.anthropic_api_key and self.standard_assistant_model)

    @field_validator(
        "assistant_thinking",
        "standard_assistant_daily_questions_per_user",
        "standard_assistant_monthly_cap_dollars",
        "standard_price_input_per_mtok",
        "standard_price_output_per_mtok",
        "standard_price_cache_write_5m_per_mtok",
        "standard_price_cache_write_1h_per_mtok",
        "standard_price_cache_read_per_mtok",
        mode="before",
    )
    @classmethod
    def _empty_means_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    # Today's exchange rate, in LBP per USD. It is saved on each receipt when it is confirmed, so
    # changing it later never changes old receipts. Update it when the rate moves.
    default_lbp_per_usd: Decimal = Decimal("89500")
