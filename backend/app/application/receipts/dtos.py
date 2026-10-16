from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.receipts.flags import review_flags
from app.domain.receipts.receipt import Receipt, ReceiptLine


@dataclass(frozen=True)
class UploadReceiptRequest:
    content: bytes
    content_type: str | None


@dataclass(frozen=True)
class ConfirmReceiptRequest:
    vendor_name: str | None
    receipt_date: date
    currency: str
    total: Decimal
    primary_category_id: int | None
    lines: Sequence[ReceiptLine] = ()
    # LBP per USD for this receipt. None keeps the rate already saved, or uses today's default.
    lbp_per_usd: Decimal | None = None


@dataclass(frozen=True)
class ReceiptView:
    """A receipt plus the review flags worked out for it."""

    receipt: Receipt
    flags: list[str]


def to_view(receipt: Receipt, today: date) -> ReceiptView:
    return ReceiptView(receipt=receipt, flags=review_flags(receipt, today))
