from dataclasses import dataclass
from decimal import Decimal

# Agreed with the user: the projection is low-confidence for the first 7 days of the month (days 1-7).
DEFAULT_LOW_CONFIDENCE_DAYS = 7


@dataclass(frozen=True)
class PaceProjection:
    projected: Decimal
    low_confidence: bool


def project_month_end(
    spent_so_far: Decimal,
    days_elapsed: int,
    days_in_month: int,
    low_confidence_days: int = DEFAULT_LOW_CONFIDENCE_DAYS,
) -> PaceProjection:
    """Rule-based projection: spent_so_far / days_elapsed * days_in_month."""
    if days_in_month <= 0:
        raise ValueError("days_in_month must be positive")
    if not 1 <= days_elapsed <= days_in_month:
        raise ValueError("days_elapsed must be between 1 and days_in_month")
    if spent_so_far < 0:
        raise ValueError("spent_so_far cannot be negative")

    projected = spent_so_far / days_elapsed * days_in_month
    return PaceProjection(projected=projected, low_confidence=days_elapsed <= low_confidence_days)
