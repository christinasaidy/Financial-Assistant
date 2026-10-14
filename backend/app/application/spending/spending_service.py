from decimal import Decimal

from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.application.spending.dtos import CategoryAmount, CurrencySummary, MonthlySummary
from app.domain.receipts.status import ReceiptStatus
from app.domain.shared.currency import Currency
from app.domain.spending.summary import Breakdown, breakdown, combined_breakdown, month_range, rounded

UNCATEGORIZED = "Uncategorized"


class SpendingService:
    """Read-only spending figures for the Home screen and the category chart."""

    def __init__(self, uow: UnitOfWorkFactory, default_lbp_per_usd: Decimal) -> None:
        self._uow = uow
        self._default_lbp_per_usd = default_lbp_per_usd  # only for receipts that have no saved rate

    def monthly_summary(self, user_id: int, year: int, month: int, display_currency: Currency) -> MonthlySummary:
        start, end = month_range(year, month)
        with self._uow(user_id) as work:
            receipts = work.receipts.list_confirmed_between(start, end)
            awaiting_review = work.receipts.count_with_status(ReceiptStatus.NEEDS_REVIEW)
            names = {category.id: category.name for category in work.categories.list_all()}

        def summarize(result: Breakdown) -> CurrencySummary:
            result = rounded(result)
            categories = [
                CategoryAmount(category_id, names.get(category_id, UNCATEGORIZED), amount)
                for category_id, amount in result.by_category.items()
            ]
            categories.sort(key=lambda item: (-item.amount, item.name))
            return CurrencySummary(result.currency, result.total, categories, result.adjustments, result.receipt_count)

        per_currency = [breakdown(receipts, currency) for currency in Currency]
        return MonthlySummary(
            month=start,
            combined=summarize(combined_breakdown(receipts, display_currency, self._default_lbp_per_usd)),
            by_currency=[summarize(result) for result in per_currency if result.receipt_count],
            awaiting_review=awaiting_review,
            converted_at_current_rate=sum(
                1 for r in receipts if r.lbp_per_usd is None and r.currency not in (None, display_currency)
            ),
            current_lbp_per_usd=self._default_lbp_per_usd,
        )
