from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.container import Container
from app.api.dependencies import get_container, get_current_user_id
from app.api.spending.schemas import MonthlySummaryOut
from app.domain.shared.currency import Currency

router = APIRouter(prefix="/spending", tags=["spending"])


@router.get("/summary", response_model=MonthlySummaryOut)
def monthly_summary(
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-10"])] = None,
    currency: Literal["USD", "LBP"] = "USD",
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> MonthlySummaryOut:
    """Spending for one month (default: this month). `combined` is everything converted into `currency`,
    each receipt at its own saved rate; `by_currency` has the exact amounts per currency."""
    if month is None:
        today = date.today()
        year, month_number = today.year, today.month
    else:
        year, month_number = (int(part) for part in month.split("-"))
    summary = container.spending.monthly_summary(user_id, year, month_number, Currency(currency))
    return MonthlySummaryOut.from_summary(summary)
