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


def normalize_size(amount: Decimal | None, unit: str | None) -> tuple[Decimal | None, str | None]:
    """Convert a size to its base unit. Anything missing or unrecognised becomes (None, None)."""
    if amount is None or unit is None or amount <= 0:
        return None, None
    try:
        base_unit, factor = _UNIT_FACTORS[unit.strip().lower()]
    except KeyError:
        return None, None
    return amount * factor, base_unit
