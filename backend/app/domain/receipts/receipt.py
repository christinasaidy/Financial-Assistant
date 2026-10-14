from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.domain.receipts.errors import InvalidReceipt
from app.domain.receipts.normalization import BASE_UNITS
from app.domain.receipts.status import ReceiptStatus
from app.domain.shared.currency import Currency

# Upper bounds that keep values inside the database column sizes.
MAX_AMOUNT = Decimal("9999999999999999.99")  # NUMERIC(18, 2)
MAX_QUANTITY = Decimal("9999999.999")  # NUMERIC(10, 3)
MAX_SIZE = Decimal("999999999.999")  # NUMERIC(12, 3)


@dataclass(frozen=True)
class ReceiptLine:
    description: str
    line_total: Decimal
    quantity: Decimal = Decimal(1)
    unit_price: Decimal | None = None
    normalized_name: str | None = None
    size_amount: Decimal | None = None
    size_unit: str | None = None
    category_id: int | None = None
    id: int | None = None


@dataclass(frozen=True)
class Receipt:
    id: int
    status: ReceiptStatus
    vendor_name: str | None
    receipt_date: date | None
    currency: Currency | None
    total: Decimal | None
    primary_category_id: int | None
    file_path: str | None
    created_at: datetime
    lines: tuple[ReceiptLine, ...] = ()
    # LBP per USD saved when the receipt was confirmed, so it is converted at the rate of its own time.
    lbp_per_usd: Decimal | None = None

    @property
    def lines_total(self) -> Decimal:
        return sum((line.line_total for line in self.lines), Decimal(0))


def validate_line(line: ReceiptLine) -> None:
    if not line.description.strip():
        raise InvalidReceipt("Every line needs a description")
    if not 0 < line.quantity <= MAX_QUANTITY:
        raise InvalidReceipt("Quantity must be greater than zero")
    if not 0 <= line.line_total <= MAX_AMOUNT:
        raise InvalidReceipt("Line total cannot be negative")
    if line.unit_price is not None and not 0 <= line.unit_price <= MAX_AMOUNT:
        raise InvalidReceipt("Unit price cannot be negative")
    if (line.size_amount is None) != (line.size_unit is None):
        raise InvalidReceipt("A size needs both an amount and a unit")
    if line.size_amount is not None:
        if not 0 < line.size_amount <= MAX_SIZE:
            raise InvalidReceipt("Size must be greater than zero")
        if line.size_unit not in BASE_UNITS:
            raise InvalidReceipt(f"Size unit must be one of: {', '.join(BASE_UNITS)}")


def validate_draft(total: Decimal | None, lines: Sequence[ReceiptLine]) -> None:
    """Check that values read by the vision model can be stored as a draft.

    A draft may have gaps (no date, no total), but any value it does have must be sane.
    """
    if total is not None and not 0 <= total <= MAX_AMOUNT:
        raise InvalidReceipt("Total is out of range")
    for line in lines:
        validate_line(line)


def validate_confirmation(currency: str, total: Decimal, lines: Sequence[ReceiptLine]) -> Currency:
    """Check the values a user confirms. Returns the currency as a domain value."""
    try:
        valid_currency = Currency(currency)
    except ValueError:
        raise InvalidReceipt("Currency must be USD or LBP") from None
    if not 0 <= total <= MAX_AMOUNT:
        raise InvalidReceipt("Total cannot be negative")
    for line in lines:
        validate_line(line)
    return valid_currency
