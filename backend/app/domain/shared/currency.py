from enum import StrEnum


class Currency(StrEnum):
    """Receipt currencies. Amounts are never mixed across currencies silently."""

    USD = "USD"
    LBP = "LBP"
