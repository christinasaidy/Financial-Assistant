from datetime import date
from decimal import Decimal

from sqlalchemy import Connection, text

from app.domain.budgets.budget import Budget
from app.domain.shared.currency import Currency


class SqlBudgetRepository:
    """Works on a connection already scoped to one user; rows are owned by `app_user_id()`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def list_up_to(self, month: date) -> list[Budget]:
        rows = self._conn.execute(
            text(
                "SELECT category_id, month, currency, limit_amount FROM budgets "
                "WHERE month <= :month ORDER BY category_id, month"
            ),
            {"month": month},
        ).all()
        return [Budget(row.category_id, row.month, Currency(row.currency), row.limit_amount) for row in rows]

    def set(self, category_id: int, month: date, currency: Currency, limit_amount: Decimal) -> None:
        self._conn.execute(
            text(
                """
                INSERT INTO budgets (user_id, category_id, month, currency, limit_amount)
                VALUES (app_user_id(), :category_id, :month, :currency, :limit_amount)
                ON CONFLICT (user_id, category_id, month)
                DO UPDATE SET currency = EXCLUDED.currency, limit_amount = EXCLUDED.limit_amount, updated_at = now()
                """
            ),
            {"category_id": category_id, "month": month, "currency": currency.value, "limit_amount": limit_amount},
        )

    def delete_category(self, category_id: int) -> int:
        return self._conn.execute(
            text("DELETE FROM budgets WHERE category_id = :category_id"), {"category_id": category_id}
        ).rowcount
