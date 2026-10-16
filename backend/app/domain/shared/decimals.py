"""How many decimal places the database stores, and checking values against that.

Agreed policy (2026-10-16, after the code review): a value typed by the user with more decimal places than
can be stored is refused with a clear message, never silently rounded and never left to crash the database.
Values read by the vision model are rounded to the stored precision instead, since a review step follows.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MONEY_PLACES = 2  # NUMERIC(18, 2)
QUANTITY_PLACES = 3  # NUMERIC(10, 3) and the size column NUMERIC(12, 3)
RATE_PLACES = 6  # NUMERIC(18, 6)


def fits(value: Decimal, places: int) -> bool:
    """A finite number with no more significant decimal places than `places` (1.50 counts as 1.5).
    Absurdly large numbers, which cannot even be rounded, do not fit either."""
    if not value.is_finite():
        return False
    try:
        return value == value.quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)
    except InvalidOperation:
        return False


def rounded(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)
