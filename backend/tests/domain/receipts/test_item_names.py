"""Stable item names (branch feature/better-item-names, decisions approved by the user on 2026-10-16).

The expected values below are the worked examples the user approved. Do not change them to make a test pass.
"""

from decimal import Decimal

import pytest

from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt, to_draft_lines
from app.domain.receipts.normalization import (
    clean_extracted_name,
    match_known_name,
    name_key,
    names_for_prompt,
    normalize_brand,
)

GROCERIES, DINING, HOUSEHOLD = 1, 2, 3
IDS = {"groceries": GROCERIES, "dining": DINING, "household": HOUSEHOLD}


def saved_name(model_name, known_names):
    """What is saved for a line whose name the model read as `model_name`."""
    line = ExtractedLine(description="x", line_total=Decimal(1), normalized_name=model_name)
    extracted = ExtractedReceipt(lines=(line,))
    return to_draft_lines(extracted, {}, IDS, known_names)[0].normalized_name


# --- The approved table: what the model returns, the user's names, what is saved ---


@pytest.mark.parametrize(
    ("model_name", "known_names", "expected"),
    [
        ("Oil  Olive", ["olive oil"], "olive oil"),  # same words in another order: the user's spelling
        ("small water", ["water"], "water"),  # size word removed, then matched
        ("water heater", ["water"], "water heater"),  # no partial match
        ("water", ["water heater"], "water"),  # no partial match the other way either
        ("pizza 2pcs large", [], "pizza"),  # size token and size word removed
        ("milk", [], "milk"),
        (None, ["milk"], None),  # nothing read: no name (flagged for review, as before)
        ("   ", ["milk"], None),
    ],
)
def test_the_name_saved_for_a_line(model_name, known_names, expected):
    assert saved_name(model_name, known_names) == expected


# --- Category memory compares names the same way ---


def suggested_category(model_name, history, model_category=None):
    line = ExtractedLine(description="x", line_total=Decimal(1), normalized_name=model_name, category=model_category)
    return to_draft_lines(ExtractedReceipt(lines=(line,)), history, IDS, ())[0].category_id


def test_category_memory_finds_the_same_words_in_another_order():
    # The user confirmed "olive oil" as Groceries; the new line comes back as "oil olive".
    assert suggested_category("oil olive", {name_key("olive oil"): [GROCERIES]}) == GROCERIES


def test_category_memory_never_matches_part_of_a_name():
    # The user confirmed "water" as Dining; "water heater" is another product: the model's own suggestion applies.
    assert suggested_category("water heater", {name_key("water"): [DINING]}, "Household") == HOUSEHOLD


# --- The pieces ---


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Water SMALL", "water"),
        ("large  big medium pizza", "pizza"),
        ("milk 1l", "milk"),
        ("milk 1.5L", "milk"),
        ("spaghetti 500g", "spaghetti"),
        ("bread 7pc", "bread"),
        ("rolls 6pcs", "rolls"),
        ("small", None),  # nothing left
        ("1l", None),
        ("7 up", "7 up"),  # a number on its own is not a size: never removed
        ("smallest pizza", "smallest pizza"),  # only whole words are removed
    ],
)
def test_size_words_and_size_tokens_are_removed_from_the_models_name(raw, expected):
    assert clean_extracted_name(raw) == expected


def test_name_key_ignores_order_case_and_spacing_only():
    assert name_key("Olive  Oil") == name_key("oil olive")
    assert name_key("water") != name_key("water heater")
    assert name_key("tea") != name_key("tea tea")  # words are not merged


def test_the_first_matching_known_name_wins_and_otherwise_the_name_is_kept():
    assert match_known_name("oil olive", ["olive oil", "oil olive"]) == "olive oil"
    assert match_known_name("labneh", ["laban"]) == "labneh"
    assert match_known_name(None, ["laban"]) is None


def test_names_for_the_prompt_keep_order_skip_long_names_and_stop_at_the_limit():
    names = ["milk", "taanayel low fat milk", "olive oil", "a b c", "tea", "x"]
    assert names_for_prompt(names, limit=4) == ["milk", "olive oil", "a b c", "tea"]
    assert names_for_prompt([], limit=200) == []


@pytest.mark.parametrize(("raw", "expected"), [(" Barilla ", "barilla"), ("Le  Charcutier", "le charcutier"),
                                               ("", None), ("  ", None), (None, None)])  # fmt: skip
def test_brands_are_lower_cased_and_tidied(raw, expected):
    assert normalize_brand(raw) == expected


def test_the_extracted_brand_is_kept_on_the_draft_line():
    line = ExtractedLine(description="BARILLA SPAGHETTI #5 500G", line_total=Decimal("3.18"),
                         normalized_name="spaghetti", brand=" Barilla ")  # fmt: skip
    (draft,) = to_draft_lines(ExtractedReceipt(lines=(line,)), {}, IDS, ())
    assert (draft.normalized_name, draft.brand) == ("spaghetti", "barilla")
