from decimal import Decimal

import pytest

from app.domain.budgets.pace import project_month_end


def test_projects_linearly_to_month_end():
    result = project_month_end(Decimal("150"), days_elapsed=10, days_in_month=30)
    assert result.projected == Decimal("450")
    assert not result.low_confidence


def test_low_confidence_early_in_the_month():
    result = project_month_end(Decimal("40"), days_elapsed=3, days_in_month=30)
    assert result.low_confidence


def test_confidence_threshold_is_configurable():
    result = project_month_end(Decimal("40"), 3, 30, min_days_for_confidence=3)
    assert not result.low_confidence


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
