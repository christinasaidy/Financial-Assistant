import re
from collections.abc import Sequence
from decimal import Decimal

# Sizes are stored in a base unit so prices can be compared per size (scope section 5.1).
BASE_UNITS = ("ml", "g", "pcs")

_UNIT_FACTORS: dict[str, tuple[str, int]] = {
    "ml": ("ml", 1),
    "cl": ("ml", 10),
    "l": ("ml", 1000),
    "g": ("g", 1),
    "kg": ("g", 1000),
    "pcs": ("pcs", 1),
    "pc": ("pcs", 1),
    "piece": ("pcs", 1),
    "pieces": ("pcs", 1),
}


def normalize_product_name(raw: str | None) -> str | None:
    """Lower-case and collapse spaces. Used only for item lookups and category memory."""
    if raw is None:
        return None
    name = " ".join(raw.lower().split())
    return name or None


# --- Stable item names (feature/better-item-names, approved by the user 2026-10-16) ---
# The name is the generic product type ("milk", "spaghetti", "manakish"); brand, size and small/large are not
# part of it. The vision model is told so; the code below enforces what it can and makes matching stable.

MAX_NAME_WORDS = 3  # only names this short are offered to the model for reuse
_SIZE_WORDS = frozenset({"small", "medium", "large", "big"})
# A number glued to a size unit: "1l", "1.5L", "500g", "7pc", "6pcs". A number alone ("7 up") is not a size.
_SIZE_TOKEN = re.compile(r"\d+(?:[.,]\d+)?(?:" + "|".join(sorted(_UNIT_FACTORS, key=len, reverse=True)) + ")")


def clean_extracted_name(raw: str | None) -> str | None:
    """The model's name, normalised, without size words or size tokens. None if nothing is left."""
    name = normalize_product_name(raw)
    if name is None:
        return None
    words = [word for word in name.split() if word not in _SIZE_WORDS and not _SIZE_TOKEN.fullmatch(word)]
    return " ".join(words) or None


def name_key(name: str) -> str:
    """What two names must share to be the same product: the same words, in any order. Never a part of a name:
    "water" and "water heater" have different keys."""
    return " ".join(sorted(name.lower().split()))


def match_known_name(name: str | None, known_names: Sequence[str]) -> str | None:
    """The user's existing spelling of the same name (same words, any order), else the name itself."""
    if name is None:
        return None
    key = name_key(name)
    return next((known for known in known_names if name_key(known) == key), name)


def names_for_prompt(names: Sequence[str], limit: int) -> list[str]:
    """The user's names to offer the model for reuse: in the given order (most recently used first), skipping
    names longer than MAX_NAME_WORDS (older, less generic ones), at most `limit`."""
    return [name for name in names if len(name.split()) <= MAX_NAME_WORDS][:limit]


def normalize_brand(raw: str | None) -> str | None:
    """Brands are compared ignoring case and spacing, like names."""
    return normalize_product_name(raw)


def normalize_size(amount: Decimal | None, unit: str | None) -> tuple[Decimal | None, str | None]:
    """Convert a size to its base unit. Anything missing or unrecognised becomes (None, None)."""
    if amount is None or unit is None or amount <= 0:
        return None, None
    try:
        base_unit, factor = _UNIT_FACTORS[unit.strip().lower()]
    except KeyError:
        return None, None
    return amount * factor, base_unit
