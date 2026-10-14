from decimal import Decimal

import pytest

from app.domain.budgets.pace import project_month_end


def test_projects_linearly_to_month_end():
    result = project_month_end(Decimal("150"), days_elapsed=10, days_in_month=30)
    assert result.projected == Decimal("450")
    assert not result.low_confidence


def test_low_confidence_for_the_first_seven_days_including_day_seven():
    # Agreed with the user: days 1-7 are low-confidence, day 8 onwards is not.
    assert project_month_end(Decimal("40"), days_elapsed=1, days_in_month=30).low_confidence
    assert project_month_end(Decimal("40"), days_elapsed=7, days_in_month=30).low_confidence
    assert not project_month_end(Decimal("40"), days_elapsed=8, days_in_month=30).low_confidence


def test_low_confidence_period_is_configurable():
    assert project_month_end(Decimal("40"), 3, 30, low_confidence_days=3).low_confidence
    assert not project_month_end(Decimal("40"), 4, 30, low_confidence_days=3).low_confidence


@pytest.mark.parametrize(
    ("spent", "elapsed", "days"),
    [
        (Decimal("10"), 0, 30),
        (Decimal("10"), 31, 30),
        (Decimal("-1"), 5, 30),
        (Decimal("10"), 5, 0),
    ],
)
def test_invalid_input_is_rejected(spent, elapsed, days):
    with pytest.raises(ValueError):
        project_month_end(spent, elapsed, days)
