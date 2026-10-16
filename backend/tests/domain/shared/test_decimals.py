"""The decimal policy agreed after the 2026-10-15 code review: typed values with more decimal places than the
database stores are refused; values read by the model are rounded."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.budgets.budget import validate_limit
from app.domain.budgets.errors import InvalidBudget
from app.domain.receipts.errors import InvalidReceipt
from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt, rounded_for_storage
from app.domain.receipts.receipt import ReceiptLine, validate_confirmation, validate_line
from app.domain.shared.decimals import fits
from app.domain.shared.exchange_rate import InvalidExchangeRate, validate_rate
from app.domain.spending.errors import InvalidMonth
from app.domain.spending.summary import month_range


@pytest.mark.parametrize(
    ("value", "places", "expected"),
    [
        ("1.5", 2, True),
        ("1.50", 2, True),
        ("1.500", 2, True),  # trailing zeros are not extra precision
        ("1.005", 2, False),
        ("0.001", 3, True),
        ("0.0001", 3, False),
        ("89500.123456", 6, True),
        ("0.0000001", 6, False),
        ("NaN", 2, False),
        ("Infinity", 2, False),
        ("1e30", 2, False),  # too large to even round
    ],
)
def test_fits(value, places, expected):
    assert fits(Decimal(value), places) is expected


# --- The examples from the code review: each one used to be silently rounded or to crash the database ---


def line(**overrides):
    return ReceiptLine(**{"description": "milk", "line_total": Decimal("4.30"), **overrides})


def test_a_total_of_1_005_is_refused_not_rounded_to_1_01():
    with pytest.raises(InvalidReceipt, match="2 decimal places"):
        validate_confirmation("USD", Decimal("1.005"), [])


def test_a_quantity_of_0_0001_is_refused():
    with pytest.raises(InvalidReceipt, match="3 decimal places"):
        validate_line(line(quantity=Decimal("0.0001")))


def test_a_budget_of_0_001_is_refused():
    with pytest.raises(InvalidBudget, match="2 decimal places"):
        validate_limit(Decimal("0.001"))


def test_a_rate_of_0_0000001_is_refused():
    with pytest.raises(InvalidExchangeRate):
        validate_rate(Decimal("0.0000001"))


@pytest.mark.parametrize(
    "bad",
    [
        {"line_total": Decimal("1.234")},
        {"unit_price": Decimal("0.005")},
        {"size_amount": Decimal("0.0005"), "size_unit": "ml"},
        {"line_total": Decimal("NaN")},
    ],
)
def test_other_values_with_too_many_decimals_are_refused(bad):
    with pytest.raises(InvalidReceipt):
        validate_line(line(**bad))


def test_values_at_the_stored_precision_are_accepted():
    validate_confirmation("USD", Decimal("9.37"), [line(quantity=Decimal("0.75"), unit_price=Decimal("5.73"))])
    validate_limit(Decimal("400.50"))
    validate_rate(Decimal("89500.123456"))


# --- Model output is rounded instead ---


def test_what_the_model_reads_is_rounded_to_the_stored_precision():
    extracted = ExtractedReceipt(
        total=Decimal("1.005"),
        lines=(
            ExtractedLine(
                description="milk",
                line_total=Decimal("2.155"),
                quantity=Decimal("1.0005"),
                unit_price=Decimal("2.154"),
                size_amount=Decimal("0.3333"),
                size_unit="l",
            ),
        ),
    )
    result = rounded_for_storage(extracted)
    assert result.total == Decimal("1.01")
    (only,) = result.lines
    assert (only.line_total, only.quantity, only.unit_price) == (Decimal("2.16"), Decimal("1.001"), Decimal("2.15"))
    # The size is not rounded in litres: precision applies to base units, after conversion (second review,
    # finding 1). See tests/infrastructure/extraction/test_extraction_pipeline.py.
    assert (only.size_amount, only.size_unit) == (Decimal("0.3333"), "l")


def test_rounding_keeps_missing_values_missing():
    result = rounded_for_storage(ExtractedReceipt(total=None, lines=(ExtractedLine("x", Decimal("1")),)))
    assert result.total is None
    assert result.lines[0].unit_price is None


# --- Months (code review finding 11) ---


@pytest.mark.parametrize(("year", "month"), [(0, 1), (9999, 12), (2026, 13), (2026, 0), (1899, 12)])
def test_months_that_cannot_be_represented_are_refused(year, month):
    with pytest.raises(InvalidMonth):
        month_range(year, month)


@pytest.mark.parametrize(
    ("year", "month", "expected"),
    [
        (2026, 12, (date(2026, 12, 1), date(2027, 1, 1))),
        (2027, 1, (date(2027, 1, 1), date(2027, 2, 1))),
        (2028, 2, (date(2028, 2, 1), date(2028, 3, 1))),  # leap year
        (9998, 12, (date(9998, 12, 1), date(9999, 1, 1))),  # the last supported month
    ],
)
def test_ordinary_and_edge_months_work(year, month, expected):
    assert month_range(year, month) == expected
