from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.budgets.schemas import MONTH_PATTERN, BudgetIn, BudgetStatusOut
from app.api.container import Container
from app.api.dependencies import get_container, get_current_user_id
from app.application.budgets.dtos import SetBudgetRequest
from app.domain.shared.currency import Currency

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _year_month(value: str) -> tuple[int, int]:
    year, month = value.split("-")
    return int(year), int(month)


@router.get("", response_model=list[BudgetStatusOut])
def list_budgets(
    month: Annotated[str | None, Query(pattern=MONTH_PATTERN, examples=["2026-10"])] = None,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> list[BudgetStatusOut]:
    """Every budget that applies to the month (default: this month), with how much is used.
    `pace` is only filled in for the current month."""
    today = date.today()
    year, month_number = _year_month(month) if month else (today.year, today.month)
    statuses = container.budgets.list_for_month(user_id, year, month_number)
    return [BudgetStatusOut.from_status(item) for item in statuses]


@router.put("/{category_id}", response_model=BudgetStatusOut)
def set_budget(
    category_id: int,
    body: BudgetIn,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> BudgetStatusOut:
    """Set the category's budget from `month` onwards. Earlier months keep their amount."""
    year, month_number = _year_month(body.month)
    request = SetBudgetRequest(category_id, year, month_number, Currency(body.currency), body.limit_amount)
    return BudgetStatusOut.from_status(container.budgets.set_budget(user_id, request))


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    category_id: int,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> Response:
    """Remove the category's budget completely, for every month."""
    container.budgets.delete_budget(user_id, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
