"""The whole path a model answer takes before it is saved as a draft: schema check (parsing.py) -> rounding to
the stored precision -> normalisation into draft lines -> the same validation the database relies on.

Second code review (2026-10-16), finding 1: sizes are stored in base units (ml, g, pcs) with 3 decimal places, so
they must be converted before they are rounded. Rounding in the model's unit lost precision (0.3333 L became
333.000 ml) or the whole size (0.0004 kg became nothing).
"""

from decimal import Decimal

import pytest

from app.domain.receipts.extraction import rounded_for_storage, to_draft_lines
from app.domain.receipts.receipt import validate_draft
from app.infrastructure.extraction.parsing import parse_extraction


def pipeline(**line_fields):
    extracted = rounded_for_storage(
        parse_extraction({"total": "1.005", "lines": [{"description": "x", "line_total": "1", **line_fields}]})
    )
    lines = to_draft_lines(extracted, category_history={}, category_ids_by_name={})
    validate_draft(extracted.total, lines)  # what is about to be saved must be storable
    return extracted, lines[0]


def size(amount, unit):
    _, line = pipeline(size_amount=amount, size_unit=unit)
    return line.size_amount, line.size_unit


@pytest.mark.parametrize(
    ("amount", "unit", "expected"),
    [
        # The review's examples.
        ("0.3333", "L", (Decimal("333.300"), "ml")),
        ("0.0004", "kg", (Decimal("0.400"), "g")),
        ("0.3333", "ml", (Decimal("0.333"), "ml")),
        # Other fractional units in the model's own unit.
        ("33.3333", "cl", (Decimal("333.333"), "ml")),
        ("1.23456", "l", (Decimal("1234.560"), "ml")),
        ("0.0015", "KG", (Decimal("1.500"), "g")),
        # Already in a base unit: converted once (factor 1), only rounded.
        ("250", "ml", (Decimal("250"), "ml")),
        ("500.0004", "g", (Decimal("500.000"), "g")),
        ("6", "pcs", (Decimal("6"), "pcs")),
        ("7", "PC", (Decimal("7"), "pcs")),
        # A number with an exponent, as JSON may carry it.
        ("1E+0", "L", (Decimal("1000"), "ml")),
    ],
)
def test_sizes_are_converted_to_base_units_before_they_are_rounded(amount, unit, expected):
    assert size(amount, unit) == expected


@pytest.mark.parametrize(
    ("amount", "unit"),
    [
        (None, "ml"),  # no amount
        ("500", None),  # no unit: never guessed
        ("12", "oz"),  # a unit we do not convert
        ("0", "ml"),
        ("-1", "L"),
        # Positive, but below what the column can hold even in base units (0.0004 ml rounds to 0.000).
        # Treated like any other unusable size: dropped, the line is kept.
        ("0.0004", "ml"),
        ("0.0000004", "L"),
    ],
)
def test_unusable_sizes_are_dropped_as_a_pair_and_the_line_is_kept(amount, unit):
    _, line = pipeline(size_amount=amount, size_unit=unit)
    assert (line.size_amount, line.size_unit) == (None, None)
    assert line.description == "x"


def test_smallest_storable_size_survives():
    assert size("0.0000005", "L") == (Decimal("0.001"), "ml")  # 0.0005 ml rounds half up to 0.001


def test_money_and_quantities_keep_the_agreed_rounding():
    extracted, line = pipeline(
        line_total="2.155", quantity="1.0005", unit_price="2.154", size_amount="0.3333", size_unit="l"
    )
    assert extracted.total == Decimal("1.01")
    assert (line.line_total, line.quantity, line.unit_price) == (Decimal("2.16"), Decimal("1.001"), Decimal("2.15"))
    assert (line.size_amount, line.size_unit) == (Decimal("333.300"), "ml")
