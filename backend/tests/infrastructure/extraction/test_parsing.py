from datetime import date
from decimal import Decimal

import pytest

from app.domain.receipts.errors import ExtractionFailed
from app.infrastructure.extraction.parsing import parse_extraction

VALID = {
    "vendor_name": " Spinneys ",
    "receipt_date": "2026-10-01",
    "currency": "usd",
    "total": "12.50",
    "lines": [
        {
            "description": "LABAN 1L",
            "normalized_name": "laban",
            "size_amount": 1,
            "size_unit": "l",
            "line_total": "2.50",
        },
        {"description": "   ", "line_total": 1},  # blank lines are dropped
    ],
}


def test_valid_output_is_parsed_with_exact_decimals():
    receipt = parse_extraction(VALID)
    assert receipt.vendor_name == "Spinneys"
    assert receipt.receipt_date == date(2026, 10, 1)
    assert receipt.currency == "USD"
    assert receipt.total == Decimal("12.50")
    assert len(receipt.lines) == 1
    assert receipt.lines[0].line_total == Decimal("2.50")
    assert receipt.lines[0].quantity == Decimal(1)


def test_unreadable_date_or_currency_is_left_empty_not_fatal():
    receipt = parse_extraction({**VALID, "receipt_date": "01/10/26?", "currency": "L.L."})
    assert receipt.receipt_date is None
    assert receipt.currency is None
    assert receipt.total == Decimal("12.50")


def test_minimal_output_is_accepted():
    assert parse_extraction({"lines": []}).lines == ()


@pytest.mark.parametrize(
    "bad",
    [
        "not an object",
        {"lines": "nope"},
        {"total": -5, "lines": []},
        {"lines": [{"description": "x"}]},  # line_total is required
        {"lines": [{"description": "x", "line_total": -1}]},
        {"lines": [{"description": "x", "line_total": 1, "quantity": 0}]},
        {"lines": [{"description": "x", "line_total": "abc"}]},
    ],
)
def test_output_that_breaks_the_schema_is_rejected(bad):
    with pytest.raises(ExtractionFailed):
        parse_extraction(bad)
