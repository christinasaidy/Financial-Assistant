"""Schema validation of the vision model's JSON (scope section 5.1)."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.domain.receipts.errors import ExtractionFailed
from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt


class _Line(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = Field(min_length=1)
    line_total: Decimal = Field(ge=0)
    quantity: Decimal = Field(default=Decimal(1), gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    normalized_name: str | None = None
    size_amount: Decimal | None = None
    size_unit: str | None = None
    category: str | None = None


class _Receipt(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vendor_name: str | None = None
    receipt_date: date | None = None
    currency: Literal["USD", "LBP"] | None = None
    total: Decimal | None = Field(default=None, ge=0)
    lines: list[_Line]  # required, as in the schema sent to Gemini; [] is allowed

    # An unreadable date or currency is left empty for the user to fill in on the review
    # screen. It should not throw away an otherwise good extraction.
    @field_validator("receipt_date", mode="before")
    @classmethod
    def _lenient_date(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip())
            except ValueError:
                return None
        return value

    @field_validator("currency", mode="before")
    @classmethod
    def _lenient_currency(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip().upper()
            return value if value in ("USD", "LBP") else None
        return value


def _find_nul(value: object, where: str = "") -> str | None:
    """Where in the answer a string holds a NUL character (U+0000), if anywhere. PostgreSQL can store it
    neither in a text column nor in the raw_extraction JSONB."""
    if isinstance(value, str):
        return where or "(root)" if "\x00" in value else None
    items = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
    for key, item in items:
        found = _find_nul(item, f"{where}.{key}" if where else str(key))
        if found is not None:
            return found
    return None


def parse_extraction(data: object) -> ExtractedReceipt:
    """Turn the model's decoded JSON into an ExtractedReceipt, or raise ExtractionFailed."""
    # Refused rather than cleaned, so the original receipt text is never silently altered; like any other
    # unusable answer it is retried once and then the receipt is marked failed for manual entry.
    if (where := _find_nul(data)) is not None:
        raise ExtractionFailed(f"The model's output contains a NUL character: {where}")
    try:
        receipt = _Receipt.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "(root)"
        raise ExtractionFailed(
            f"The model's output did not match the receipt schema: {where}: {first['msg']} "
            f"({exc.error_count()} problem(s))"
        ) from exc
    return ExtractedReceipt(
        vendor_name=(receipt.vendor_name or "").strip() or None,
        receipt_date=receipt.receipt_date,
        currency=receipt.currency,
        total=receipt.total,
        lines=tuple(ExtractedLine(**line.model_dump()) for line in receipt.lines if line.description.strip()),
    )
