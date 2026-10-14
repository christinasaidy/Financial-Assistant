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
    lines: list[_Line] = []

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


def parse_extraction(data: object) -> ExtractedReceipt:
    """Turn the model's decoded JSON into an ExtractedReceipt, or raise ExtractionFailed."""
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
