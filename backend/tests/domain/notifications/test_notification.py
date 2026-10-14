"""Which notification a budget gets, and the wording. The examples and their outcomes were approved by
the user on 2026-10-14, before this code was written. Do not change an expected value to make a test pass."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.budgets.budget import budget_state
from app.domain.notifications.notification import (
    BudgetSnapshot,
    NotificationKind,
    budget_notification,
    format_money,
    receipt_failed_notification,
    receipt_ready_notification,
)
from app.domain.shared.currency import Currency

GROCERIES = 1


def groceries(spent: str, limit: str = "400", projected: str | None = None, low_confidence: bool = False):
    spent_d, limit_d = Decimal(spent), Decimal(limit)
    return BudgetSnapshot(
        category_id=GROCERIES,
        category_name="Groceries",
        month=date(2026, 10, 1),
        currency=Currency.USD,
        limit_amount=limit_d,
        spent=spent_d,
        percent_used=(spent_d / limit_d * 100).quantize(Decimal("0.1")),
        state=budget_state(spent_d, limit_d),
        projected=None if projected is None else Decimal(projected),
        pace_low_confidence=low_confidence,
    )


# --- Example 1: Groceries, budget $400. Approved: $330 near (83%), $410 limit reached ($10 over) ---


def test_example_1_at_330_near():
    notification = budget_notification(groceries("330", projected="852.50"))
    assert notification.kind is NotificationKind.BUDGET_NEAR  # near beats pace
    assert notification.body == "Groceries: you've used 83% of your $400 budget."
    assert notification.dedup_key == "budget_near:1:2026-10"
    assert notification.data == {"category_id": 1, "month": "2026-10"}


def test_example_1_at_410_limit_reached():
    notification = budget_notification(groceries("410", projected="1059.17"))
    assert notification.kind is NotificationKind.BUDGET_LIMIT_REACHED
    assert notification.body == "Groceries: you've reached your $400 budget ($10 over)."
    assert notification.dedup_key == "budget_limit_reached:1:2026-10"


# --- Example 2: a jump from $300 to $420. Approved: only "limit reached" ---


def test_example_2_a_jump_past_the_limit_is_only_limit_reached():
    assert budget_notification(groceries("420")).kind is NotificationKind.BUDGET_LIMIT_REACHED


# --- Example 3: pace. Approved: 12 Oct at $200 -> pace warning about $517; 5 Oct -> nothing ---


def test_example_3_pace_on_12_october():
    notification = budget_notification(groceries("200", projected="516.67"))
    assert notification.kind is NotificationKind.PACE_WARNING
    assert notification.body == "At this pace you'll spend about $517 on Groceries this month (budget $400)."
    assert notification.dedup_key == "pace_warning:1:2026-10"


def test_example_3_no_pace_warning_in_the_first_7_days():
    assert budget_notification(groceries("200", projected="1240.00", low_confidence=True)) is None


# --- The rest of the rules ---


def test_nothing_when_under_80_percent_and_on_pace():
    assert budget_notification(groceries("100", projected="258.33")) is None


def test_no_pace_without_a_projection():
    assert budget_notification(groceries("200", projected=None)) is None


def test_exactly_at_the_limit_says_reached_without_an_over_amount():
    assert budget_notification(groceries("400")).body == "Groceries: you've reached your $400 budget."


def test_an_lbp_budget_is_worded_in_lbp():
    snapshot = BudgetSnapshot(
        GROCERIES, "Groceries", date(2026, 10, 1), Currency.LBP, Decimal("9000000"), Decimal("9500000"),
        Decimal("105.6"), budget_state(Decimal("9500000"), Decimal("9000000")), None, True,
    )  # fmt: skip
    assert budget_notification(snapshot).body == (
        "Groceries: you've reached your 9,000,000 LBP budget (500,000 LBP over)."
    )


@pytest.mark.parametrize(
    ("amount", "currency", "expected"),
    [
        ("400", Currency.USD, "$400"),
        ("10.5", Currency.USD, "$10.50"),
        ("1234", Currency.USD, "$1,234"),
        ("1350000", Currency.LBP, "1,350,000 LBP"),
        ("0.004", Currency.USD, "$0"),
    ],
)
def test_money_formatting(amount, currency, expected):
    assert format_money(Decimal(amount), currency) == expected


def test_receipt_notifications():
    ready = receipt_ready_notification(42, "Spinneys")
    assert (ready.kind, ready.body, ready.dedup_key, ready.data) == (
        NotificationKind.RECEIPT_READY,
        "Your Spinneys receipt is ready to review.",
        "receipt_ready:42",
        {"receipt_id": 42},
    )
    assert receipt_ready_notification(42, None).body == "Your receipt is ready to review."
    failed = receipt_failed_notification(42, date(2026, 10, 12))
    assert failed.body == "We couldn't read your receipt from 12 Oct. You can enter it by hand."
    assert failed.dedup_key == "receipt_failed:42"
