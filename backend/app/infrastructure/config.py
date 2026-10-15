from decimal import Decimal

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

    # Today's exchange rate, in LBP per USD. It is saved on each receipt when it is confirmed, so
    # changing it later never changes old receipts. Update it when the rate moves.
    default_lbp_per_usd: Decimal = Decimal("89500")
