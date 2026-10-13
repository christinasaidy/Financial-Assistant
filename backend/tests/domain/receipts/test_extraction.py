from decimal import Decimal

from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt, to_draft_lines

GROCERIES, DINING = 1, 2
IDS = {"groceries": GROCERIES, "dining": DINING}


def draft(line: ExtractedLine, history=None):
    return to_draft_lines(ExtractedReceipt(lines=(line,)), history or {}, IDS)[0]


def test_line_is_normalised():
    line = draft(
        ExtractedLine(
            description="  LABAN AYRAN 1L ",
            line_total=Decimal("2.5"),
            normalized_name=" Laban  Ayran",
            size_amount=Decimal(1),
            size_unit="L",
        )
    )
    assert line.description == "LABAN AYRAN 1L"  # original text kept, only trimmed
    assert line.normalized_name == "laban ayran"
    assert (line.size_amount, line.size_unit) == (Decimal(1000), "ml")


def test_model_suggestion_is_used_when_there_is_no_history():
    line = draft(ExtractedLine(description="x", line_total=Decimal(1), normalized_name="laban", category=" Groceries "))
    assert line.category_id == GROCERIES


def test_category_memory_wins_over_the_model():
    line = draft(
        ExtractedLine(description="x", line_total=Decimal(1), normalized_name="laban", category="Groceries"),
        history={"laban": [DINING, DINING, GROCERIES]},
    )
    assert line.category_id == DINING


def test_unknown_category_name_and_no_history_means_no_suggestion():
    line = draft(ExtractedLine(description="x", line_total=Decimal(1), normalized_name="laban", category="Pets"))
    assert line.category_id is None


def test_line_without_a_name_gets_no_memory_suggestion():
    line = draft(ExtractedLine(description="x", line_total=Decimal(1), category="Dining"), history={"laban": [GROCERIES]})
    assert line.normalized_name is None
    assert line.category_id == DINING
