"""The batch-4 worked examples (approved by the user on 2026-11-16; today Wednesday 2028-01-12) run on real
PostgreSQL as the app runs them. Do not change an expected value to make a test pass."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.assistant.prompt import UserNames
from tests.integration.test_assistant_sql import (  # noqa: F401 (fixtures)
    client,
    container,
    one_value,
    post_receipt,
    run_as_on,
    settings,
    sign_in,
)

TODAY = date(2028, 1, 12)  # a Wednesday, the evaluation's date
NAMES = UserNames(items=["sushi", "steak", "panadol"],
                  vendors=["Lakkis", "Burger King", "Sushi Star", "Pharmacie Mazloum", "Pharmacie Nassar", "Spinneys"],
                  categories=["Groceries", "Dining", "Health"])  # fmt: skip

# One receipt per day, each a different power of two, so a total shows exactly which days were counted.
DAYS = ["2025-12-31", "2026-01-12", "2026-01-13", "2026-12-31", "2027-01-01", "2027-05-31", "2027-06-01",
        "2027-08-31", "2027-09-01", "2027-12-22", "2027-12-23", "2027-12-31", "2028-01-01", "2028-01-12"]  # fmt: skip


@pytest.fixture
def one_receipt_a_day(client, sign_in):
    headers, user_id = sign_in()
    for power, day in enumerate(DAYS):
        post_receipt(client, headers, day, "Spinneys", str(2**power))
    return user_id


@pytest.mark.parametrize(
    ("where", "days"),
    [
        # el sene el madye: the previous calendar year
        (("receipt_date >= date_trunc('year', CURRENT_DATE) - INTERVAL '1 year' "
          "AND receipt_date < date_trunc('year', CURRENT_DATE)"), [d for d in DAYS if d.startswith("2027")]),
        # mn sentain la hala2: the last 2 years, like the last N months
        ("receipt_date > CURRENT_DATE - INTERVAL '2 years' AND receipt_date <= CURRENT_DATE",
         [d for d in DAYS if d >= "2026-01-13"]),
        # ekher kam jem3a: the last 3 weeks (21 days, today included)
        ("receipt_date > CURRENT_DATE - 21 AND receipt_date <= CURRENT_DATE", [d for d in DAYS if d >= "2027-12-23"]),
        # mn el sayfiye la hala2: from 1 June of the most recent summer
        ("receipt_date >= '2027-06-01'", [d for d in DAYS if d >= "2027-06-01"]),
        # bl sayf: June to August of the most recent summer
        ("receipt_date >= '2027-06-01' AND receipt_date < '2027-09-01'", ["2027-06-01", "2027-08-31"]),
    ],
)  # fmt: skip
def test_the_batch4_periods_count_exactly_the_approved_days(container, one_receipt_a_day, where, days):
    spent = one_value(run_as_on(container, one_receipt_a_day, f"SELECT SUM(total) FROM receipts WHERE {where}",
                                today=TODAY, names=NAMES))  # fmt: skip
    assert spent == sum(2 ** DAYS.index(day) for day in days)


@pytest.fixture
def receipts(client, sign_in):
    headers, user_id = sign_in()
    for day, vendor, total, lines, category in [
        ("2025-11-20", "Lakkis", "30.00", [], "Dining"),  # more than 2 years ago
        ("2026-03-02", "Lakkis", "25.00", [], "Dining"),
        ("2027-10-09", "Lakkis", "40.00", [], "Dining"),
        ("2028-01-03", "Lakkis", "35.00", [], "Dining"),
        ("2028-01-10", "Lakkis", "28.00", [], "Dining"),
        ("2027-09-28", "Burger King", "9.00", [], "Dining"),  # before the last 3 complete months
        ("2027-10-04", "Burger King", "8.00", [], "Dining"),
        ("2027-10-21", "Burger King", "8.50", [], "Dining"),
        ("2027-11-15", "Burger King", "9.50", [], "Dining"),
        ("2027-12-30", "Burger King", "7.00", [], "Dining"),
        ("2028-01-02", "Burger King", "8.00", [], "Dining"),  # this month: not complete
        ("2028-01-05", "Burger King", "8.00", [], "Dining"),
        ("2027-11-02", "Sushi Star", "24.00", [("sushi", None, None, "1", "24.00", "24.00")], "Dining"),
        ("2027-12-18", "Sushi Star", "30.00", [("sushi", None, None, "1", "30.00", "30.00")], "Dining"),
        ("2027-12-27", "Spinneys", "18.00", [("steak", "500", "g", "1", "18.00", "18.00")], "Groceries"),
        ("2027-12-29", "Pharmacie Mazloum", "4.00", [("panadol", "24", "pcs", "1", "4.00", "4.00")], "Health"),
        ("2028-01-04", "Pharmacie Nassar", "6.00", [("panadol", "24", "pcs", "1", "6.00", "6.00")], "Health"),
        ("2028-01-08", "Pharmacie Mazloum", "5.00", [("panadol", "24", "pcs", "1", "5.00", "5.00")], "Health"),
    ]:  # fmt: skip
        post_receipt(client, headers, day, vendor, total, lines, category=category)
    return user_id


def rows(container, user_id, sql):
    return run_as_on(container, user_id, sql, today=TODAY, names=NAMES).rows


def test_visits_in_the_last_two_years(container, receipts):  # 2: mn sentain la hala2 aday rehet aal Lakkis
    sql = ("SELECT COUNT(DISTINCT receipt_id) AS visits FROM receipts WHERE vendor = 'Lakkis' "
           "AND receipt_date > CURRENT_DATE - INTERVAL '2 years' AND receipt_date <= CURRENT_DATE")  # fmt: skip
    assert rows(container, receipts, sql) == [(4,)]


def test_how_often_with_no_period_is_visits_per_month_over_the_last_three_complete_months(container, receipts):  # 5
    sql = ("SELECT ROUND(COUNT(DISTINCT receipt_id) / 3.0, 1) AS visits_per_month FROM receipts "
           "WHERE vendor = 'Burger King' AND receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '3 months' "
           "AND receipt_date < date_trunc('month', CURRENT_DATE)")  # fmt: skip
    assert rows(container, receipts, sql) == [(Decimal("1.3"),)]  # 4 visits in October to December


def test_the_last_time_an_item_was_bought(container, receipts):  # 6: aymata ekher mara akalet sushi
    sql = "SELECT MAX(receipt_date) AS last_time FROM purchases WHERE item_name = 'sushi'"
    assert rows(container, receipts, sql) == [(date(2027, 12, 18),)]


def test_the_last_time_at_a_shop(container, receipts):  # 6, a shop
    sql = "SELECT MAX(receipt_date) AS last_time FROM receipts WHERE vendor = 'Lakkis'"
    assert rows(container, receipts, sql) == [(date(2028, 1, 10),)]


def test_when_did_i_go_lists_the_dates_in_the_period(container, receipts):  # 7: aymata rehet aal Lakkis hal sene
    sql = ("SELECT receipt_date, vendor FROM receipts WHERE vendor = 'Lakkis' "
           "AND receipt_date >= date_trunc('year', CURRENT_DATE) ORDER BY receipt_date")  # fmt: skip
    assert rows(container, receipts, sql) == [(date(2028, 1, 3), "Lakkis"), (date(2028, 1, 10), "Lakkis")]


def test_a_pharmacy_is_every_shop_named_pharmacie(container, receipts):  # 7b: aymata rehet 3al pharmacie hal sene
    sql = ("SELECT receipt_date, vendor FROM receipts WHERE vendor IN ('Pharmacie Mazloum', 'Pharmacie Nassar') "
           "AND receipt_date >= date_trunc('year', CURRENT_DATE) ORDER BY receipt_date")  # fmt: skip
    assert rows(container, receipts, sql) == [(date(2028, 1, 4), "Pharmacie Nassar"),
                                              (date(2028, 1, 8), "Pharmacie Mazloum")]  # fmt: skip


def test_where_the_money_went_in_the_last_few_weeks(container, receipts):  # 3: ekher kam jemaa, by category
    sql = ("SELECT category, currency, SUM(amount) AS total_spent, SUM(amount_usd) AS total_spent_usd "
           "FROM category_spending WHERE receipt_date > CURRENT_DATE - 21 AND receipt_date <= CURRENT_DATE "
           "GROUP BY category, currency ORDER BY total_spent_usd DESC")  # fmt: skip
    assert rows(container, receipts, sql) == [
        ("Dining", "USD", Decimal("86.00"), Decimal("86.00")),  # Lakkis 35 + 28, Burger King 7 + 8 + 8
        ("Groceries", "USD", Decimal("18.00"), Decimal("18.00")),
        ("Health", "USD", Decimal("15.00"), Decimal("15.00")),
    ]


def test_a_summary_of_the_last_two_years_is_spending_by_category(container, receipts):  # 8: tolkhis aan ekher sentain
    sql = ("SELECT category, currency, SUM(amount) AS total_spent, SUM(amount_usd) AS total_spent_usd "
           "FROM category_spending WHERE receipt_date > CURRENT_DATE - INTERVAL '2 years' "
           "AND receipt_date <= CURRENT_DATE GROUP BY category, currency ORDER BY total_spent_usd DESC")  # fmt: skip
    assert rows(container, receipts, sql) == [
        ("Dining", "USD", Decimal("240.00"), Decimal("240.00")),  # Lakkis 128, Burger King 58, Sushi Star 54
        ("Groceries", "USD", Decimal("18.00"), Decimal("18.00")),
        ("Health", "USD", Decimal("15.00"), Decimal("15.00")),
    ]


def test_the_cheapest_brand_compares_every_brand_per_100_g(client, sign_in, container):  # approved 2026-11-16
    headers, user_id = sign_in()
    for day, vendor, line in [
        ("2027-11-03", "Spinneys", ("rice", "1000", "g", "1", "2.40", "2.40", "uncle ben's")),
        ("2027-12-01", "Spinneys", ("rice", "1000", "g", "1", "2.60", "2.60", "uncle ben's")),
        ("2027-12-10", "Spinneys", ("rice", "2000", "g", "1", "4.00", "4.00", "al wadi")),
        ("2028-01-05", "Spinneys", ("rice", "1000", "g", "1", "2.10", "2.10", "sunwhite")),
        ("2028-01-06", "Spinneys", ("rice", "1000", "g", "1", "1.50", "1.50")),  # no brand printed: left out
    ]:  # fmt: skip
        post_receipt(client, headers, day, vendor, line[5], [line])
    sql = ("SELECT brand, currency, COUNT(*) AS purchase_count, "
           "ROUND(AVG(COALESCE(unit_price, line_total / quantity) / size_amount * 100), 2) AS average_price_per_100 "
           "FROM purchases WHERE item_name = 'rice' AND size_unit IN ('g', 'ml') AND brand IS NOT NULL "
           "GROUP BY brand, currency ORDER BY average_price_per_100, brand")  # fmt: skip
    names = UserNames(items=["rice"], vendors=["Spinneys"], categories=["Groceries"])
    assert run_as_on(container, user_id, sql, today=TODAY, names=names).rows == [
        ("al wadi", "USD", 1, Decimal("0.20")), ("sunwhite", "USD", 1, Decimal("0.21")),
        ("uncle ben's", "USD", 2, Decimal("0.25"))]  # fmt: skip
