"""The three example months and their expected numbers were checked and approved by the user on
2026-10-14, before this code was written. Do not change an expected value to make a test pass.

Choosing which receipts count (confirmed only, by printed date) is the repository's job and is tested
in tests/integration/test_spending_flow.py; these tests start from the receipts that do count.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.receipts.receipt import Receipt, ReceiptLine
from app.domain.receipts.status import ReceiptStatus
from app.domain.shared.currency import Currency
from app.domain.spending.summary import breakdown, combined_breakdown, month_range, rounded

GROCERIES, HOUSEHOLD, DINING, HEALTH = 1, 2, 3, 4
UNCATEGORIZED = None
USD, LBP = Currency.USD, Currency.LBP


def receipt(currency, total, category=None, lines=(), rate=None) -> Receipt:
    return Receipt(
        id=0,
        status=ReceiptStatus.CONFIRMED,
        vendor_name="shop",
        receipt_date=date(2026, 10, 1),
        currency=currency,
        total=Decimal(total),
        primary_category_id=category,
        file_path=None,
        created_at=datetime.now(UTC),
        lines=tuple(
            ReceiptLine(description=name, line_total=Decimal(amount), category_id=cat) for name, amount, cat in lines
        ),
        lbp_per_usd=None if rate is None else Decimal(rate),
    )


# --- Example 1 (October): the basics. Approved: G 8, H 12, D 15, Uncategorized 8.50, +3.00, overall 46.50 ---

OCTOBER = [
    receipt(USD, "23.00", lines=[("Milk", "5", GROCERIES), ("Bread", "3", GROCERIES), ("Detergent", "12", HOUSEHOLD)]),
    receipt(USD, "15.00", category=DINING),  # café, no lines
    receipt(USD, "8.50"),  # pharmacy, no lines, no category
]


def test_example_1_october():
    result = breakdown(OCTOBER, USD)
    assert result.total == Decimal("46.50")
    assert result.by_category == {
        GROCERIES: Decimal("8.00"),
        HOUSEHOLD: Decimal("12.00"),
        DINING: Decimal("15.00"),
        UNCATEGORIZED: Decimal("8.50"),
    }
    assert result.adjustments == Decimal("3.00")
    assert result.receipt_count == 3


# --- Example 2 (November): items fall back to the receipt's category; a discount. Approved: G 10, Health 10, -1.20 ---


def test_example_2_november():
    carrefour = receipt(
        USD,
        "18.80",
        category=GROCERIES,
        lines=[("Laban", "4", None), ("Chips", "6", None), ("Shampoo", "10", HEALTH)],
    )
    result = breakdown([carrefour], USD)
    assert result.by_category == {GROCERIES: Decimal("10"), HEALTH: Decimal("10")}
    assert result.adjustments == Decimal("-1.20")
    assert result.total == Decimal("18.80")


# --- Example 3 (December): two currencies, kept apart. Approved: USD Dining 12; LBP G 1,350,000,
#     Uncategorized 250,000, +50,000, overall 1,650,000 ---

DECEMBER = [
    receipt(LBP, "450000", category=GROCERIES, rate="89500"),
    receipt(USD, "12.00", category=DINING, rate="89500"),
    receipt(LBP, "1200000", lines=[("Rice", "900000", GROCERIES), ("Oil", "250000", None)], rate="89500"),
]


def test_example_3_december_usd_part():
    result = breakdown(DECEMBER, USD)
    assert result.total == Decimal("12.00")
    assert result.by_category == {DINING: Decimal("12.00")}
    assert result.adjustments == 0
    assert result.receipt_count == 1


def test_example_3_december_lbp_part():
    result = breakdown(DECEMBER, LBP)
    assert result.total == Decimal("1650000")
    assert result.by_category == {GROCERIES: Decimal("1350000"), UNCATEGORIZED: Decimal("250000")}
    assert result.adjustments == Decimal("50000")
    assert result.receipt_count == 2


# --- The combined total (agreed: one total in the user's currency, each receipt at its own saved rate).
#     These numbers follow from Example 3 at 89,500 LBP per USD. ---


def test_example_3_combined_in_usd():
    result = rounded(combined_breakdown(DECEMBER, USD, fallback_lbp_per_usd=Decimal("89500")))
    assert result.total == Decimal("30.44")  # 12 + 1,650,000 / 89,500 = 30.4358
    assert result.by_category == {
        DINING: Decimal("12.00"),
        GROCERIES: Decimal("15.08"),  # 1,350,000 / 89,500
        UNCATEGORIZED: Decimal("2.79"),  # 250,000 / 89,500
    }
    assert result.adjustments == Decimal("0.57")  # what is left, so the shown numbers add up
    assert result.receipt_count == 3


def test_example_3_combined_in_lbp():
    result = rounded(combined_breakdown(DECEMBER, LBP, fallback_lbp_per_usd=Decimal("89500")))
    assert result.total == Decimal("2724000.00")  # 1,650,000 + 12 x 89,500
    assert result.by_category[DINING] == Decimal("1074000.00")


def test_each_receipt_is_converted_at_its_own_saved_rate():
    old = receipt(LBP, "150000", category=GROCERIES, rate="15000")  # confirmed when the rate was 15,000
    new = receipt(LBP, "179000", category=GROCERIES, rate="89500")
    result = combined_breakdown([old, new], USD, fallback_lbp_per_usd=Decimal("89500"))
    assert result.total == Decimal("12")  # 10 + 2


def test_todays_rate_is_used_only_when_a_receipt_has_none():
    result = combined_breakdown([receipt(LBP, "179000", category=GROCERIES)], USD, Decimal("89500"))
    assert result.total == Decimal("2")


# --- Rounding and months ---


def test_rounded_numbers_still_add_up_to_the_total():
    three_thirds = [receipt(LBP, "1", category=cat, rate="3") for cat in (GROCERIES, DINING, HEALTH)]
    result = rounded(combined_breakdown(three_thirds, USD, Decimal("3")))
    assert result.total == Decimal("1.00")
    assert sum(result.by_category.values()) + result.adjustments == result.total


def test_an_empty_month_is_all_zero():
    result = rounded(breakdown([], USD))
    assert (result.total, result.by_category, result.adjustments, result.receipt_count) == (0, {}, 0, 0)


def test_month_range_end_is_the_first_day_of_the_next_month():
    assert month_range(2026, 10) == (date(2026, 10, 1), date(2026, 11, 1))
    assert month_range(2026, 12) == (date(2026, 12, 1), date(2027, 1, 1))
