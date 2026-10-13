from decimal import Decimal

import pytest

from app.domain.receipts.normalization import normalize_product_name, normalize_size


def test_product_name_is_lowercased_and_spaces_collapsed():
    assert normalize_product_name("  Laban   AYRAN ") == "laban ayran"


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_empty_product_name_becomes_none(empty):
    assert normalize_product_name(empty) is None


@pytest.mark.parametrize(
    ("amount", "unit", "expected"),
    [
        ("250", "ml", (Decimal("250"), "ml")),
        ("1", "L", (Decimal("1000"), "ml")),
        ("33", "cl", (Decimal("330"), "ml")),
        ("2", "kg", (Decimal("2000"), "g")),
        ("500", " G ", (Decimal("500"), "g")),
        ("6", "pieces", (Decimal("6"), "pcs")),
    ],
)
def test_sizes_are_converted_to_base_units(amount, unit, expected):
    assert normalize_size(Decimal(amount), unit) == expected


@pytest.mark.parametrize(("amount", "unit"), [(None, "ml"), (Decimal(1), None), (Decimal(0), "ml"), (Decimal(1), "oz")])
def test_missing_or_unknown_sizes_are_dropped_not_guessed(amount, unit):
    assert normalize_size(amount, unit) == (None, None)
