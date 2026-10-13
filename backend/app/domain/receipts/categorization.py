from collections import Counter
from collections.abc import Sequence

# A category is referenced by id. None means "Uncategorized".
CategoryId = int | None


def effective_category(line_category_id: CategoryId, receipt_category_id: CategoryId) -> CategoryId:
    """Category used for spending: the line's own, else the receipt's, else Uncategorized (None)."""
    if line_category_id is not None:
        return line_category_id
    return receipt_category_id


def suggest_category(past_categories: Sequence[int]) -> int | None:
    """Category memory: the category the user most often confirmed for a product.

    `past_categories` lists the user's previously confirmed categories for lines with the
    same normalized name, oldest first. Ties go to the most recent. Returns None when there
    is no history, so the caller falls back to the vision model's own suggestion.
    """
    if not past_categories:
        return None
    counts = Counter(past_categories)
    best = max(counts.values())
    for category_id in reversed(past_categories):
        if counts[category_id] == best:
            return category_id
    return None  # unreachable
