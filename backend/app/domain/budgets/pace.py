from dataclasses import dataclass
from decimal import Decimal

# The scope hides or flags the projection during the first 5-7 days of the month.
DEFAULT_MIN_DAYS_FOR_CONFIDENCE = 7


@dataclass(frozen=True)
class PaceProjection:
    projected: Decimal
    low_confidence: bool


def project_month_end(
    spent_so_far: Decimal,
    days_elapsed: int,
    days_in_month: int,
    min_days_for_confidence: int = DEFAULT_MIN_DAYS_FOR_CONFIDENCE,
) -> PaceProjection:
    """Rule-based projection: spent_so_far / days_elapsed * days_in_month."""
    if days_in_month <= 0:
        raise ValueError("days_in_month must be positive")
    if not 1 <= days_elapsed <= days_in_month:
        raise ValueError("days_elapsed must be between 1 and days_in_month")
    if spent_so_far < 0:
        raise ValueError("spent_so_far cannot be negative")

    projected = spent_so_far / days_elapsed * days_in_month
    return PaceProjection(projected=projected, low_confidence=days_elapsed < min_days_for_confidence)
