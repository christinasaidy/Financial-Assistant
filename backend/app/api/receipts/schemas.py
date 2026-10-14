"""HTTP shapes for receipts. Money and quantities are Decimal, sent as JSON strings to stay exact."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.application.receipts.dtos import ConfirmReceiptRequest, ReceiptView
from app.domain.receipts.receipt import Receipt, ReceiptLine


class LineIn(BaseModel):
    description: str
    line_total: Decimal
    quantity: Decimal = Decimal(1)
    unit_price: Decimal | None = None
    normalized_name: str | None = None
    size_amount: Decimal | None = None
    size_unit: str | None = None
    category_id: int | None = None


class ConfirmBody(BaseModel):
    vendor_name: str | None = None
    receipt_date: date
    currency: str
    total: Decimal
    primary_category_id: int | None = None
    lines: list[LineIn] = []
    # LBP per USD. Leave it out to keep the saved rate, or to use today's default on a new receipt.
    lbp_per_usd: Decimal | None = None

    def to_request(self) -> ConfirmReceiptRequest:
        return ConfirmReceiptRequest(
            vendor_name=self.vendor_name,
            receipt_date=self.receipt_date,
            currency=self.currency,
            total=self.total,
            primary_category_id=self.primary_category_id,
            lines=[ReceiptLine(**line.model_dump()) for line in self.lines],
            lbp_per_usd=self.lbp_per_usd,
        )


class LineOut(BaseModel):
    id: int | None
    description: str
    line_total: Decimal
    quantity: Decimal
    unit_price: Decimal | None
    normalized_name: str | None
    size_amount: Decimal | None
    size_unit: str | None
    category_id: int | None


class ReceiptSummaryOut(BaseModel):
    id: int
    status: str
    vendor_name: str | None
    receipt_date: date | None
    currency: str | None
    total: Decimal | None
    primary_category_id: int | None
    lbp_per_usd: Decimal | None
    has_file: bool
    created_at: datetime

    @classmethod
    def from_receipt(cls, receipt: Receipt) -> "ReceiptSummaryOut":
        return cls(**_summary_fields(receipt))


class ReceiptOut(ReceiptSummaryOut):
    lines: list[LineOut]
    lines_total: Decimal
    flags: list[str]

    @classmethod
    def from_view(cls, view: ReceiptView) -> "ReceiptOut":
        receipt = view.receipt
        return cls(
            **_summary_fields(receipt),
            lines=[LineOut(**vars(line)) for line in receipt.lines],
            lines_total=receipt.lines_total,
            flags=view.flags,
        )


def _summary_fields(receipt: Receipt) -> dict[str, object]:
    return {
        "id": receipt.id,
        "status": receipt.status.value,
        "vendor_name": receipt.vendor_name,
        "receipt_date": receipt.receipt_date,
        "currency": receipt.currency.value if receipt.currency else None,
        "total": receipt.total,
        "primary_category_id": receipt.primary_category_id,
        "lbp_per_usd": receipt.lbp_per_usd,
        "has_file": receipt.file_path is not None,
        "created_at": receipt.created_at,
    }
