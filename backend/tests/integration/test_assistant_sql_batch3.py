"""The batch-3 worked examples (approved by the user on 2026-11-15; today Wednesday 2027-02-10) run on real
PostgreSQL as the app runs them. Do not change an expected value to make a test pass."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.assistant.prompt import UserNames
from tests.integration.test_assistant_sql import (  # noqa: F401 (fixtures)
    PERIOD_DAYS,
    UNIT_PRICE,
    client,
    container,
    one_receipt_a_day,
    one_value,
    post_receipt,
    run_as_on,
    settings,
    sign_in,
)

PER_LITRE = f"{UNIT_PRICE} / size_amount * 1000"
NAMES = UserNames(items=["chicken", "tawouk", "fuel", "labneh", "shampoo", "bread"],
                  vendors=["Spinneys", "Carrefour", "Happy", "Roadster Diner", "Kababji", "Total", "Foodies", "Coop"],
                  categories=["Groceries", "Dining", "Transport"])  # fmt: skip


@pytest.mark.parametrize(
    ("where", "days"),
    [
        ("receipt_date = CURRENT_DATE - 2", ["2027-02-08"]),  # abel mbereh: the day before yesterday
        ("receipt_date >= '2027-02-04'", [d for d in PERIOD_DAYS if d >= "2027-02-04"]),  # men el khamis: since Thursday
        ("receipt_date >= '2027-02-03'", [d for d in PERIOD_DAYS if d >= "2027-02-03"]),  # since Wednesday, asked on one
        ("receipt_date >= CURRENT_DATE - 1", ["2027-02-09", "2027-02-10"]),  # men mberha la lyom
    ],
)  # fmt: skip
def test_the_batch3_periods_count_exactly_the_approved_days(container, one_receipt_a_day, where, days):
    spent = one_value(run_as_on(container, one_receipt_a_day, f"SELECT SUM(total) FROM receipts WHERE {where}"))
    assert spent == sum(2 ** PERIOD_DAYS.index(day) for day in days)


@pytest.fixture
def receipts(client, sign_in):
    headers, user_id = sign_in()
    for day, vendor, total, lines, category in [
        ("2026-10-01", "Carrefour", "4.50", [("chicken", "1000", "g", "1", "4.50", "4.50")], "Groceries"),
        ("2026-11-15", "Spinneys", "4.00", [("chicken", "1000", "g", "1", "4.00", "4.00")], "Groceries"),
        ("2027-01-25", "Spinneys", "4.20", [("chicken", "1000", "g", "1", "4.20", "4.20")], "Groceries"),
        ("2026-11-20", "Kababji", "15.00", [("tawouk", None, None, "3", "5.00", "15.00")], "Dining"),
        ("2026-12-03", "Kababji", "5.00", [("tawouk", None, None, "1", "5.00", "5.00")], "Dining"),
        ("2027-01-12", "Kababji", "10.00", [("tawouk", None, None, "2", "5.00", "10.00")], "Dining"),
        ("2027-01-05", "Roadster Diner", "20.00", [], "Dining"),
        ("2027-01-20", "Roadster Diner", "18.00", [], "Dining"),
        ("2027-01-10", "Total", "20.00", [("fuel", "20000", "ml", "1", "20.00", "20.00")], "Transport"),
        ("2027-02-08", "Total", "22.00", [("fuel", "20000", "ml", "1", "22.00", "22.00")], "Transport"),
        ("2027-02-01", "Spinneys", "6.50", [("labneh", "500", "g", "1", "2.50", "2.50"),
                                            ("shampoo", "400", "ml", "1", "4.00", "4.00", "dove")], "Groceries"),
        ("2027-02-02", "Carrefour", "2.00", [("labneh", "500", "g", "1", "2.00", "2.00")], "Groceries"),
        ("2027-02-03", "Happy", "8.60", [("labneh", "1000", "g", "1", "5.00", "5.00"),
                                         ("shampoo", "400", "ml", "1", "3.60", "3.60", "dove")], "Groceries"),
        ("2027-02-04", "Foodies", "1.50", [("bread", None, None, "1", "1.50", "1.50", "wooden bakery")], "Groceries"),
        ("2027-02-05", "Coop", "2.20", [("bread", None, None, "1", "1.20", "1.20", "wooden bakery"),
                                        ("bread", None, None, "1", "1.00", "1.00", "pain d'or")], "Groceries"),
    ]:  # fmt: skip
        post_receipt(client, headers, day, vendor, total, lines, category=category)
    return user_id


def rows(container, user_id, sql):
    return run_as_on(container, user_id, sql, names=NAMES).rows


def test_the_day_before_yesterday_is_listed_purchase_by_purchase(container, receipts):  # N1
    sql = ("SELECT receipt_date, vendor, item_name, currency, line_total FROM purchases "
           "WHERE receipt_date = CURRENT_DATE - 2 ORDER BY receipt_date")  # fmt: skip
    assert rows(container, receipts, sql) == [(date(2027, 2, 8), "Total", "fuel", "USD", Decimal("22.00"))]


def test_the_most_visited_restaurant_last_month_counts_visits(container, receipts):  # N4
    sql = ("SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM category_spending WHERE category = 'Dining' "
           "AND receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' "
           "AND receipt_date < date_trunc('month', CURRENT_DATE) GROUP BY vendor ORDER BY visits DESC LIMIT 1")  # fmt: skip
    assert rows(container, receipts, sql) == [("Roadster Diner", 2)]


def test_the_cheapest_shop_with_no_shops_named_compares_every_shop(container, receipts):  # N5
    sql = (f"SELECT vendor, currency, COUNT(*) AS purchase_count, ROUND(AVG({UNIT_PRICE} / size_amount * 100), 2) "
           "AS average_price_per_100 FROM purchases WHERE item_name = 'labneh' AND size_unit IN ('g', 'ml') "
           "GROUP BY vendor, currency ORDER BY average_price_per_100, vendor")  # fmt: skip
    assert rows(container, receipts, sql) == [
        ("Carrefour", "USD", 1, Decimal("0.40")), ("Happy", "USD", 1, Decimal("0.50")),
        ("Spinneys", "USD", 1, Decimal("0.50"))]  # fmt: skip


def test_a_price_change_compares_the_latest_purchase_with_the_one_before(container, receipts):  # N6
    """Changed requirement, approved by the user on 2026-11-19 (batch 5): both purchases are in the latest one's
    currency, which is returned (the old query compared 420,000 LBP with $4.20)."""
    where = "item_name = 'fuel' AND size_unit = 'ml'"
    latest_currency = f"(SELECT currency FROM purchases WHERE {where} ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1)"

    def one(offset: str) -> str:
        return (f"(SELECT receipt_date, currency, {PER_LITRE} AS price FROM purchases WHERE {where} AND currency = "
                f"{latest_currency} ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1{offset})")  # fmt: skip

    sql = ("SELECT latest.currency, latest.receipt_date AS latest_date, ROUND(latest.price, 2) AS latest_price, "
           "previous.receipt_date AS previous_date, ROUND(previous.price, 2) AS previous_price, "
           "ROUND((latest.price - previous.price) / NULLIF(previous.price, 0) * 100, 1) AS percent_change "
           f"FROM {one('')} AS latest, {one(' OFFSET 1')} AS previous")  # fmt: skip
    assert rows(container, receipts, sql) == [
        ("USD", date(2027, 2, 8), Decimal("1.10"), date(2027, 1, 10), Decimal("1.00"), Decimal("10.0"))]


def test_the_average_price_this_month_against_last_month(container, receipts):  # N6, "m3adal"
    sql = (f"SELECT date_trunc('month', receipt_date) AS month, ROUND(AVG({PER_LITRE}), 2) AS average_price_per_litre "
           "FROM purchases WHERE item_name = 'fuel' AND size_unit = 'ml' "
           "AND receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' GROUP BY month ORDER BY month")
    found = [(month.date() if hasattr(month, "date") else month, price) for month, price in rows(container, receipts, sql)]
    assert found == [(date(2027, 1, 1), Decimal("1.00")), (date(2027, 2, 1), Decimal("1.10"))]


def test_since_when_gives_the_first_purchase_and_the_times_since(container, receipts):  # N7
    sql = ("SELECT MIN(receipt_date) AS first_bought, COUNT(DISTINCT receipt_id) AS times FROM purchases "
           "WHERE item_name = 'chicken' AND vendor = 'Spinneys'")  # fmt: skip
    assert rows(container, receipts, sql) == [(date(2026, 11, 15), 2)]


def test_usually_per_month_is_the_last_three_complete_months_over_three(container, receipts):  # N8
    sql = ("SELECT ROUND(SUM(quantity) / 3.0, 1) AS usual_per_month FROM purchases WHERE item_name = 'tawouk' "
           "AND receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '3 months' "
           "AND receipt_date < date_trunc('month', CURRENT_DATE)")  # fmt: skip
    assert rows(container, receipts, sql) == [(Decimal("2.0"),)]


def test_one_brand_compared_between_two_shops(container, receipts):  # N9
    sql = (f"SELECT vendor, currency, COUNT(*) AS purchase_count, ROUND(AVG({UNIT_PRICE} / size_amount * 100), 2) "
           "AS average_price_per_100 FROM purchases WHERE item_name = 'shampoo' AND brand = 'dove' "
           "AND vendor IN ('Spinneys', 'Happy') AND size_unit IN ('g', 'ml') GROUP BY vendor, currency, size_unit "
           "ORDER BY vendor")  # fmt: skip
    assert rows(container, receipts, sql) == [("Happy", "USD", 1, Decimal("0.90")),
                                              ("Spinneys", "USD", 1, Decimal("1.00"))]  # fmt: skip


def test_receipts_at_restaurants_are_counted_through_their_category(container, receipts):  # N10
    sql = "SELECT COUNT(DISTINCT receipt_id) AS receipt_count FROM category_spending WHERE category = 'Dining'"
    assert rows(container, receipts, sql) == [(5,)]


def test_the_same_brand_keeps_only_brands_bought_at_both_shops(container, receipts):  # C6
    sql = (f"SELECT brand, vendor, currency, COUNT(*) AS purchase_count, ROUND(AVG({UNIT_PRICE}), 2) AS average_price "
           "FROM purchases WHERE item_name = 'bread' AND vendor IN ('Foodies', 'Coop') AND brand IN (SELECT brand FROM "
           "purchases WHERE item_name = 'bread' AND vendor IN ('Foodies', 'Coop') GROUP BY brand "
           "HAVING COUNT(DISTINCT vendor) = 2) GROUP BY brand, vendor, currency ORDER BY vendor")  # fmt: skip
    assert rows(container, receipts, sql) == [("wooden bakery", "Coop", "USD", 1, Decimal("1.20")),
                                              ("wooden bakery", "Foodies", "USD", 1, Decimal("1.50"))]  # fmt: skip
