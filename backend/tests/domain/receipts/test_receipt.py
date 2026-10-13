from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.receipts.errors import InvalidReceipt
from app.domain.receipts.flags import review_flags
from app.domain.receipts.receipt import Receipt, ReceiptLine, validate_confirmation, validate_draft, validate_line
from app.domain.receipts.status import ReceiptStatus
from app.domain.shared.currency import Currency


def line(**overrides) -> ReceiptLine:
    return ReceiptLine(**{"description": "laban", "line_total": Decimal("3"), "normalized_name": "laban", **overrides})


def receipt(**overrides) -> Receipt:
    values = {
        "id": 1,
        "status": ReceiptStatus.NEEDS_REVIEW,
        "vendor_name": "Spinneys",
        "receipt_date": date(2026, 10, 1),
        "currency": Currency.USD,
        "total": Decimal("3"),
        "primary_category_id": None,
        "file_path": None,
        "created_at": datetime.now(UTC),
        "lines": (line(),),
    }
    return Receipt(**{**values, **overrides})


def test_valid_line_passes():
    validate_line(line(quantity=Decimal("0.75"), unit_price=Decimal("4"), size_amount=Decimal(250), size_unit="ml"))


@pytest.mark.parametrize(
    "bad",
    [
        {"description": "   "},
        {"quantity": Decimal(0)},
        {"line_total": Decimal(-1)},
        {"unit_price": Decimal(-1)},
        {"size_amount": Decimal(250)},
        {"size_unit": "ml"},
        {"size_amount": Decimal(0), "size_unit": "ml"},
        {"size_amount": Decimal(1), "size_unit": "l"},  # must already be a base unit
    ],
)
def test_invalid_lines_are_rejected(bad):
    with pytest.raises(InvalidReceipt):
        validate_line(line(**bad))


def test_confirmation_returns_the_currency_and_rejects_bad_values():
    assert validate_confirmation("LBP", Decimal("450000"), [line()]) is Currency.LBP
    with pytest.raises(InvalidReceipt):
        validate_confirmation("EUR", Decimal(1), [])
    with pytest.raises(InvalidReceipt):
        validate_confirmation("USD", Decimal(-1), [])
    with pytest.raises(InvalidReceipt):
        validate_confirmation("USD", Decimal(1), [line(quantity=Decimal(0))])


def test_complete_receipt_has_no_flags():
    assert review_flags(receipt()) == []


def test_missing_values_are_flagged():
    flags = review_flags(receipt(vendor_name=None, receipt_date=None, currency=None, total=None))
    assert flags == ["missing_vendor", "missing_date", "missing_currency", "missing_total"]


def test_lines_not_adding_up_is_flagged_not_rejected():
    assert review_flags(receipt(total=Decimal("3.30"))) == ["total_mismatch"]


def test_receipt_without_lines_is_not_a_mismatch():
    assert review_flags(receipt(lines=())) == []


def test_line_without_a_normalized_name_is_flagged():
    assert review_flags(receipt(lines=(line(normalized_name=None),))) == ["line_without_name"]


def test_a_draft_may_have_gaps_but_not_impossible_values():
    validate_draft(None, [])
    validate_draft(Decimal("12.50"), [line()])
    with pytest.raises(InvalidReceipt):
        validate_draft(Decimal("1e20"), [])
    with pytest.raises(InvalidReceipt):
        validate_draft(Decimal(-1), [])
    with pytest.raises(InvalidReceipt):
        validate_draft(Decimal(1), [line(quantity=Decimal("1e9"))])
