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
        {"description": "LABAN 1L", "normalized_name": "laban", "size_amount": 1, "size_unit": "l", "line_total": "2.50"},
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


def test_a_schema_error_says_which_field_was_wrong():
    with pytest.raises(ExtractionFailed, match=r"lines\.0\.line_total"):
        parse_extraction({"lines": [{"description": "x", "line_total": "abc"}]})


# --- Code review finding 15: `lines` is required, as in the schema sent to Gemini ---


@pytest.mark.parametrize("bad", [{}, {"vendor_name": "Spinneys"}, {"something": "else"}])
def test_an_answer_without_lines_is_not_a_successful_read(bad):
    with pytest.raises(ExtractionFailed, match="lines"):
        parse_extraction(bad)


def test_an_explicit_empty_list_of_lines_is_still_accepted():
    assert parse_extraction({"vendor_name": "Spinneys", "total": "5", "lines": []}).lines == ()


@pytest.mark.parametrize(
    ("answer", "where"),
    [
        ({**VALID, "vendor_name": "Spin\u0000neys"}, "vendor_name"),
        ({"lines": [{"description": "MILK\u0000", "line_total": 1}]}, "lines.0.description"),
        (
            {"lines": [{"description": "MILK", "normalized_name": "mi\u0000lk", "line_total": 1}]},
            "lines.0.normalized_name",
        ),
        ({"lines": [{"description": "MILK", "line_total": 1, "category": "x\u0000"}]}, "lines.0.category"),
        ({"lines": [], "unexpected": ["\u0000"]}, "unexpected.0"),  # even in a field we ignore: kept in raw_extraction
    ],
)
def test_an_answer_with_a_nul_character_is_rejected_not_cleaned(answer, where):
    # Second review, finding 2: PostgreSQL cannot store U+0000 in text or JSONB.
    with pytest.raises(ExtractionFailed, match=where.replace(".", r"\.")):
        parse_extraction(answer)


def test_arabic_and_accented_text_from_the_model_is_kept_exactly():
    answer = {"vendor_name": "زعتر و زيت", "lines": [{"description": "Pâté\tمنقوشة", "line_total": 1}]}
    result = parse_extraction(answer)
    assert result.vendor_name == "زعتر و زيت"
    assert result.lines[0].description == "Pâté\tمنقوشة"
