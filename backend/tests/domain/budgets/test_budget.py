"""Budget rules. Examples 3 and 4 and their expected results were approved by the user on 2026-10-14,
before this code was written. Do not change an expected value to make a test pass."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.budgets.budget import Budget, BudgetState, budget_state, budgets_for_month, validate_limit
from app.domain.budgets.errors import InvalidBudget
from app.domain.shared.currency import Currency

GROCERIES, DINING = 1, 2


# --- Example 3: Household, budget $50. Approved: $45 near, $50 limit reached, $60 limit reached ---


@pytest.mark.parametrize(
    ("spent", "expected"),
    [
        ("45", BudgetState.NEAR),
        ("50", BudgetState.LIMIT_REACHED),
        ("60", BudgetState.LIMIT_REACHED),
    ],
)
def test_example_3_household(spent, expected):
    assert budget_state(Decimal(spent), Decimal("50")) is expected


@pytest.mark.parametrize(
    ("spent", "expected"),
    [
        ("0", BudgetState.OK),
        ("39.99", BudgetState.OK),  # just under 80%
        ("40", BudgetState.NEAR),  # exactly 80%
        ("49.99", BudgetState.NEAR),
        ("50", BudgetState.LIMIT_REACHED),  # exactly 100%
    ],
)
def test_state_boundaries(spent, expected):
    assert budget_state(Decimal(spent), Decimal("50")) is expected


# --- Example 4: a budget that repeats. Approved: Oct 400, Nov 400, Dec 350, Jan 350, Sep none ---

SET = [
    Budget(GROCERIES, date(2026, 10, 1), Currency.USD, Decimal("400")),
    Budget(GROCERIES, date(2026, 12, 1), Currency.USD, Decimal("350")),
]


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        (date(2026, 9, 1), None),
        (date(2026, 10, 1), Decimal("400")),
        (date(2026, 11, 1), Decimal("400")),
        (date(2026, 12, 1), Decimal("350")),
        (date(2027, 1, 1), Decimal("350")),
    ],
)
def test_example_4_a_budget_repeats_until_changed(month, expected):
    applying = budgets_for_month(SET, month)
    assert (applying[GROCERIES].limit_amount if GROCERIES in applying else None) == expected


def test_each_category_repeats_on_its_own():
    budgets = [*SET, Budget(DINING, date(2026, 11, 1), Currency.LBP, Decimal("9000000"))]
    applying = budgets_for_month(budgets, date(2026, 11, 1))
    assert applying[GROCERIES].limit_amount == Decimal("400")
    assert applying[DINING].currency is Currency.LBP


@pytest.mark.parametrize("bad", ["0", "-1", "1e20"])
def test_impossible_limits_are_refused(bad):
    with pytest.raises(InvalidBudget):
        validate_limit(Decimal(bad))
