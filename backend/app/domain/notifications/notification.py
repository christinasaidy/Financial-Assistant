"""In-app notifications (decisions agreed with the user on 2026-10-14).

Budget notifications, checked after anything that changes a budget's numbers, for the current month only:
- `budget_near` when a budget passes 80%, `budget_limit_reached` at 100%, and `pace_warning` when the pace
  goes over the limit after the first 7 days.
- Only the most serious one applies at a time, and each kind is sent at most once per category per month,
  even if spending drops back and crosses again. A budget that has reached its limit gets no pace warning.

Receipt notifications: `receipt_ready` when a receipt has been read and waits for review, and
`receipt_failed` when it could not be read. One per receipt.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.domain.budgets.budget import BudgetState
from app.domain.shared.currency import Currency


class NotificationKind(StrEnum):
    BUDGET_NEAR = "budget_near"
    BUDGET_LIMIT_REACHED = "budget_limit_reached"
    PACE_WARNING = "pace_warning"
    RECEIPT_READY = "receipt_ready"
    RECEIPT_FAILED = "receipt_failed"


@dataclass(frozen=True)
class NewNotification:
    kind: NotificationKind
    title: str
    body: str
    dedup_key: str  # the same key is never sent twice to the same user
    data: dict[str, object] = field(default_factory=dict)  # lets the app open the right screen


@dataclass(frozen=True)
class Notification:
    id: int
    kind: str
    title: str
    body: str
    data: dict[str, object]
    read_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class BudgetSnapshot:
    """What the budget notifications need to know about one budget in the current month."""

    category_id: int
    category_name: str
    month: date
    currency: Currency
    limit_amount: Decimal
    spent: Decimal
    percent_used: Decimal
    state: BudgetState
    projected: Decimal | None  # None when there is no pace (not the current month)
    pace_low_confidence: bool


def format_money(amount: Decimal, currency: Currency) -> str:
    """$400, $10.50, $1,234 or 1,350,000 LBP."""
    if currency is Currency.LBP:
        return f"{amount.quantize(Decimal(1), ROUND_HALF_UP):,} LBP"
    cents = amount.quantize(Decimal("0.01"), ROUND_HALF_UP)
    return f"${cents:,.0f}" if cents == cents.to_integral_value() else f"${cents:,.2f}"


def budget_notification(budget: BudgetSnapshot) -> NewNotification | None:
    """The most serious notification that applies to the budget right now, or None."""
    name, limit = budget.category_name, format_money(budget.limit_amount, budget.currency)
    period = budget.month.strftime("%Y-%m")
    data: dict[str, object] = {"category_id": budget.category_id, "month": period}

    if budget.state is BudgetState.LIMIT_REACHED:
        over = budget.spent - budget.limit_amount
        extra = f" ({format_money(over, budget.currency)} over)" if over > 0 else ""
        return NewNotification(
            NotificationKind.BUDGET_LIMIT_REACHED,
            title=f"{name} budget reached",
            body=f"{name}: you've reached your {limit} budget{extra}.",
            dedup_key=f"budget_limit_reached:{budget.category_id}:{period}",
            data=data,
        )
    if budget.state is BudgetState.NEAR:
        percent = budget.percent_used.quantize(Decimal(1), ROUND_HALF_UP)
        return NewNotification(
            NotificationKind.BUDGET_NEAR,
            title=f"{name} budget at {percent}%",
            body=f"{name}: you've used {percent}% of your {limit} budget.",
            dedup_key=f"budget_near:{budget.category_id}:{period}",
            data=data,
        )
    if budget.projected is not None and not budget.pace_low_confidence and budget.projected > budget.limit_amount:
        about = format_money(budget.projected.quantize(Decimal(1), ROUND_HALF_UP), budget.currency)
        return NewNotification(
            NotificationKind.PACE_WARNING,
            title=f"{name} on pace to go over",
            body=f"At this pace you'll spend about {about} on {name} this month (budget {limit}).",
            dedup_key=f"pace_warning:{budget.category_id}:{period}",
            data=data,
        )
    return None


def receipt_ready_notification(receipt_id: int, vendor_name: str | None) -> NewNotification:
    which = f"Your {vendor_name} receipt" if vendor_name else "Your receipt"
    return NewNotification(
        NotificationKind.RECEIPT_READY,
        title="Receipt ready to review",
        body=f"{which} is ready to review.",
        dedup_key=f"receipt_ready:{receipt_id}",
        data={"receipt_id": receipt_id},
    )


def receipt_failed_notification(receipt_id: int, uploaded_on: date) -> NewNotification:
    return NewNotification(
        NotificationKind.RECEIPT_FAILED,
        title="Receipt couldn't be read",
        body=f"We couldn't read your receipt from {uploaded_on.day} {uploaded_on:%b}. You can enter it by hand.",
        dedup_key=f"receipt_failed:{receipt_id}",
        data={"receipt_id": receipt_id},
    )
