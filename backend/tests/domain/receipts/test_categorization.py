from app.domain.receipts.categorization import effective_category, suggest_category


def test_line_category_wins():
    assert effective_category(line_category_id=3, receipt_category_id=7) == 3


def test_falls_back_to_receipt_category():
    assert effective_category(line_category_id=None, receipt_category_id=7) == 7


def test_uncategorized_when_neither_is_set():
    assert effective_category(line_category_id=None, receipt_category_id=None) is None


def test_suggestion_is_none_without_history():
    assert suggest_category([]) is None


def test_suggestion_is_the_most_frequent_category():
    assert suggest_category([1, 2, 2, 1, 2]) == 2


def test_tie_goes_to_most_recent():
    # oldest first: 1 and 2 are tied, 2 was confirmed most recently
    assert suggest_category([1, 2]) == 2
    assert suggest_category([2, 1]) == 1
