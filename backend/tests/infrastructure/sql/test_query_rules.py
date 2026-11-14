"""The answering rules (exact names, the date) and the sources query. Decisions approved by the user on 2026-11-03;
do not change an expected value to make a test pass. Nothing here runs SQL: the integration tests do."""

from datetime import date

import pytest

from app.domain.assistant.errors import QueryRejected
from app.domain.assistant.prompt import UserNames
from app.infrastructure.sql.query_rules import SqlGlotQueryRules
from app.infrastructure.sql.sql_guard import SqlGlotGuard

TODAY = date(2026, 11, 3)
NAMES = UserNames(items=["laban", "water", "water heater", "bread"], vendors=["Spinneys", "Carrefour"],
                  categories=["Groceries", "Dining", "Uncategorized", "Tax, discounts & rounding"])  # fmt: skip
rules = SqlGlotQueryRules()
guard = SqlGlotGuard()


def prepared(sql: str) -> str:
    return rules.prepare(guard.check(sql), NAMES, TODAY)


# --- The date (round 1, Q10) ---


def test_current_date_becomes_the_given_date():
    sql = prepared("SELECT SUM(total) FROM receipts WHERE receipt_date >= date_trunc('month', CURRENT_DATE)")
    assert sql == (
        "SELECT SUM(total) FROM receipts WHERE receipt_date >= DATE_TRUNC('MONTH', CAST('2026-11-03' AS DATE))"
    )


def test_the_date_used_is_the_one_given_not_the_computers_clock():
    sql = guard.check("SELECT COUNT(*) FROM receipts WHERE receipt_date = CURRENT_DATE")
    assert rules.prepare(sql, NAMES, date(2025, 1, 31)).endswith("receipt_date = CAST('2025-01-31' AS DATE)")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT now()",
        "SELECT CURRENT_TIMESTAMP",
        "SELECT COUNT(*) FROM receipts WHERE receipt_date = 'today'::date",
        "SELECT COUNT(*) FROM receipts WHERE receipt_date = DATE 'yesterday'",
        "SELECT COUNT(*) FROM receipts WHERE receipt_date < CAST('now' AS date)",
    ],
)
def test_reading_the_clock_any_other_way_is_refused(sql):
    with pytest.raises(QueryRejected, match="CURRENT_DATE"):
        prepared(sql)


def test_a_literal_date_is_left_alone():
    sql = "SELECT COUNT(*) FROM receipts WHERE receipt_date >= CAST('2026-09-01' AS DATE)"
    assert prepared(sql) == sql


# --- Exact names (round 1, Q8; round 2, Q6; examples Q6) ---


@pytest.mark.parametrize(
    ("sql", "column"),
    [
        ("SELECT SUM(line_total) FROM purchases WHERE item_name ILIKE '%water%'", "item_name"),  # E14
        ("SELECT SUM(line_total) FROM purchases WHERE item LIKE '%WATER%'", "item_name"),
        ("SELECT SUM(line_total) FROM purchases p WHERE lower(p.item_name) LIKE 'wat%'", "item_name"),
        ("SELECT SUM(total) FROM receipts WHERE vendor ILIKE '%spin%'", "vendor"),
        ("SELECT SUM(amount) FROM category_spending WHERE category LIKE 'Groc%'", "category"),
        ("SELECT SUM(line_total) FROM purchases WHERE item_name NOT ILIKE '%heater%'", "item_name"),
    ],
)
def test_loose_matching_on_names_is_refused(sql, column):
    with pytest.raises(QueryRejected, match=f"use {column} = '<name>' with a name from the list"):
        prepared(sql)


def test_the_e14_message_is_the_approved_one():
    with pytest.raises(QueryRejected) as refused:
        prepared("SELECT SUM(line_total) FROM purchases WHERE item_name ILIKE '%water%'")
    assert str(refused.value) == "Item names must match exactly: use item_name = '<name>' with a name from the list"


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("SELECT SUM(line_total) FROM purchases WHERE item_name = 'milk'", "'milk' is not one of the user's items"),
        ("SELECT SUM(line_total) FROM purchases WHERE item_name = 'manakish'", "'manakish' is not one of the user's"),
        ("SELECT SUM(total) FROM receipts WHERE vendor = 'spinneys'", "'spinneys' is not one of the user's vendors"),
        ("SELECT SUM(total) FROM receipts WHERE vendor IN ('Spinneys', 'Abou Ali')", "'Abou Ali' is not one"),
        ("SELECT SUM(amount) FROM category_spending WHERE category = 'Restaurants'", "'Restaurants' is not one"),
        ("SELECT SUM(amount) FROM category_spending WHERE 'Food' = category", "'Food' is not one"),
        ("SELECT SUM(CASE WHEN item_name = 'milk' THEN line_total END) FROM purchases", "'milk' is not one"),
    ],
)
def test_names_the_user_does_not_have_are_refused(sql, message):
    with pytest.raises(QueryRejected, match=message):
        prepared(sql)


def test_names_wrapped_in_a_function_are_refused():
    with pytest.raises(QueryRejected, match="without functions"):
        prepared("SELECT SUM(total) FROM receipts WHERE lower(vendor) = 'spinneys'")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT SUM(line_total) FROM purchases WHERE item_name = 'water'",  # E7: not the water heater
        "SELECT SUM(line_total) FROM purchases WHERE item_name = 'water heater'",
        "SELECT SUM(line_total) FROM purchases WHERE item_name IN ('laban', 'bread') AND vendor <> 'Carrefour'",
        "SELECT SUM(amount) FROM category_spending WHERE category = 'Tax, discounts & rounding'",
        "SELECT SUM(amount) FROM category_spending WHERE category = 'Uncategorized'",
        "SELECT SUM(line_total) FROM purchases WHERE brand = 'taanayel'",  # brands have no list
        "SELECT p.vendor FROM purchases p JOIN receipts r ON r.receipt_id = p.receipt_id AND r.vendor = p.vendor",
    ],
)
def test_exact_names_from_the_lists_are_accepted(sql):
    assert prepared(sql) == guard.check(sql)


# --- The sources query (round 1, Q5; examples Q3) ---


def test_an_aggregate_query_gives_every_receipt_its_filters_matched():
    sql = prepared(
        "SELECT currency, SUM(line_total) AS total_spent FROM purchases WHERE item_name = 'laban' "
        "GROUP BY currency HAVING SUM(line_total) > 1 ORDER BY 2 DESC LIMIT 3"
    )
    assert rules.sources_query(sql) == (
        "SELECT DISTINCT purchases.receipt_id AS receipt_id FROM purchases WHERE item_name = 'laban' "
        "ORDER BY 1 NULLS FIRST"
    )


def test_a_query_listing_rows_keeps_its_order_and_limit():  # E4: based on the one purchase shown
    sql = prepared(
        "SELECT receipt_date, vendor, unit_price AS latest_price FROM purchases WHERE item_name = 'laban' "
        "ORDER BY receipt_date DESC LIMIT 1"
    )
    assert rules.sources_query(sql) == (
        "SELECT DISTINCT source_receipt_id FROM (SELECT receipt_date, vendor, unit_price AS latest_price, "
        "purchases.receipt_id AS source_receipt_id FROM purchases WHERE item_name = 'laban' "
        "ORDER BY receipt_date DESC LIMIT 1) AS shown ORDER BY 1 NULLS FIRST"
    )


def test_the_first_table_alias_is_used_with_joins():
    sql = prepared(
        "SELECT COUNT(*) FROM purchases p JOIN receipts r ON r.receipt_id = p.receipt_id WHERE p.item_name = 'bread'"
    )
    assert rules.sources_query(sql).startswith("SELECT DISTINCT p.receipt_id AS receipt_id FROM purchases AS p JOIN")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT SUM(total) FROM receipts UNION ALL SELECT SUM(amount) FROM category_spending",
        "WITH t AS (SELECT total FROM receipts) SELECT SUM(total) FROM t",
        "SELECT SUM(total) FROM (SELECT total FROM receipts) AS t",
    ],
)
def test_no_sources_rather_than_wrong_ones_when_it_cannot_be_told(sql):
    assert rules.sources_query(prepared(sql)) is None


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT SUM(total) FROM receipts WHERE vendor = 'Spinneys'",
        "SELECT vendor, total FROM receipts ORDER BY total DESC LIMIT 5",
        "SELECT DISTINCT vendor FROM receipts",
    ],
)
def test_the_sources_query_passes_the_guard(sql):
    sources = rules.sources_query(prepared(sql))
    assert guard.check(sources) == sources


# --- Periods and sizes (approved 2026-11-07): the new shapes pass the guard and the rules ---


@pytest.mark.parametrize(
    ("where", "expected"),
    [
        ("receipt_date = CURRENT_DATE - 1", "receipt_date = CAST('2026-11-03' AS DATE) - 1"),
        ("receipt_date > CURRENT_DATE - 7 AND receipt_date <= CURRENT_DATE",
         "receipt_date > CAST('2026-11-03' AS DATE) - 7 AND receipt_date <= CAST('2026-11-03' AS DATE)"),
        ("receipt_date > CURRENT_DATE - INTERVAL '3 months' AND receipt_date <= CURRENT_DATE",
         "receipt_date > CAST('2026-11-03' AS DATE) - INTERVAL '3 MONTHS' AND receipt_date <= CAST('2026-11-03' AS DATE)"),
        ("receipt_date >= date_trunc('year', CURRENT_DATE)",
         "receipt_date >= DATE_TRUNC('YEAR', CAST('2026-11-03' AS DATE))"),
    ],
)  # fmt: skip
def test_the_new_rolling_periods_get_the_given_date(where, expected):
    assert prepared(f"SELECT SUM(total) FROM receipts WHERE {where}") == f"SELECT SUM(total) FROM receipts WHERE {expected}"


def test_the_size_queries_pass_the_guard_and_the_rules():
    sql = ("SELECT SUM(quantity * size_amount) FILTER (WHERE size_unit = 'g') / 1000 AS kilos, "
           "COUNT(*) FILTER (WHERE size_amount IS NULL) AS purchases_without_size "
           "FROM purchases WHERE item_name = 'bread'")  # fmt: skip
    assert "FILTER(WHERE size_amount IS NULL)" in prepared(sql).replace("FILTER (", "FILTER(")
    price = prepared("SELECT AVG(COALESCE(unit_price, line_total / quantity) / size_amount * 1000) FROM purchases "
                     "WHERE item_name = 'laban' AND size_unit = 'g'")  # fmt: skip
    assert "COALESCE(unit_price, line_total / quantity)" in price


# --- The dates the question asked for (approved 2026-11-14). Today is Tuesday 3 November 2026. ---

YESTERDAY = "receipt_date = CURRENT_DATE - 1"
OCTOBER_2025 = "receipt_date >= '2025-10-01' AND receipt_date < '2025-11-01'"
OCTOBER_2026 = "receipt_date >= '2026-10-01' AND receipt_date < '2026-11-01'"
DECEMBER_2025 = "receipt_date >= '2025-12-01' AND receipt_date < '2026-01-01'"
YEAR_2025 = "receipt_date >= '2025-01-01' AND receipt_date < '2026-01-01'"


def dates_checked(where: str, asked: str) -> None:
    rules.check_dates(prepared(f"SELECT SUM(total) FROM receipts WHERE {where}"), asked, TODAY)


@pytest.mark.parametrize(
    ("where", "asked"),
    [
        (YESTERDAY, "shu dafa3et 3al dekhan mberha"),
        (YESTERDAY, "How much did I spend on Monday?"),
        ("receipt_date = '2026-11-02'", "adde sraft nhar el tanayn"),
        (YESTERDAY, "adde sraft mbere7? bas bi Spinneys?"),  # a follow-up: its earlier question, then the question
        (OCTOBER_2026, "How much did I spend in October?"),
        (OCTOBER_2025, "adde sraft bi teshreen el awal el sene li mar2it"),
        (DECEMBER_2025, "adde sraft bi kanoun el awal"),
        (YEAR_2025, "How much did I spend last year?"),
    ],
)
def test_dates_the_question_asked_for_are_allowed(where, asked):
    dates_checked(where, asked)


@pytest.mark.parametrize("asked", ["adde sarle defe3 3al ahwe la halla2", "How much did I spend on bread?"])
def test_yesterday_is_refused_when_the_question_does_not_mention_it(asked):
    with pytest.raises(QueryRejected, match="The question does not mention yesterday: use the period it names, "
                                            "or no date filter if it names none"):  # fmt: skip
        dates_checked(YESTERDAY, asked)


def test_last_years_month_is_refused_when_this_years_has_come():
    with pytest.raises(QueryRejected, match=r"A month named without a year is the most recent one: October is "
                                            r"receipt_date >= '2026-10-01' AND receipt_date < '2026-11-01'"):  # fmt: skip
        dates_checked(OCTOBER_2025, "How much did I spend in October?")


def test_last_years_month_is_refused_in_that_same_month_this_year():
    with pytest.raises(QueryRejected, match=r"November is receipt_date >= '2026-11-01' AND receipt_date < '2026-12-01'"):
        dates_checked("receipt_date >= '2025-11-01' AND receipt_date < '2025-12-01'", "How much did I spend in November?")


def test_a_range_of_months_is_left_alone():  # only a single named month is checked
    dates_checked("receipt_date >= '2025-03-01' AND receipt_date < '2025-06-01'", "adde sraft men adar la ayyar")


# --- What the query looked at, shown under the answer (approved 2026-11-14). Today is Tuesday 3 November 2026. ---

THIS_MONTH_SQL = ("receipt_date >= date_trunc('month', CURRENT_DATE) "
                  "AND receipt_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'")  # fmt: skip
LAST_MONTH_SQL = ("receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' "
                  "AND receipt_date < date_trunc('month', CURRENT_DATE)")  # fmt: skip
NAMES_TOO = UserNames(items=["laban", "bread", "coffee"], vendors=["Spinneys", "Carrefour"],
                      categories=["Groceries", "Dining"])  # fmt: skip


@pytest.mark.parametrize(
    ("sql", "understood"),
    [
        (f"SELECT currency, SUM(total) AS total_spent FROM receipts WHERE {THIS_MONTH_SQL} GROUP BY currency",
         "Looked at: all your spending, 1–30 November 2026"),
        ("SELECT currency, SUM(amount) AS total_spent FROM category_spending "
         f"WHERE category = 'Groceries' AND {LAST_MONTH_SQL} GROUP BY currency",
         "Looked at: category Groceries, 1–31 October 2026"),
        ("SELECT vendor, currency, COUNT(*) AS purchase_count, "
         "ROUND(AVG(COALESCE(unit_price, line_total / quantity) / size_amount * 100), 2) AS average_price "
         "FROM purchases WHERE item_name = 'laban' AND vendor IN ('Spinneys', 'Carrefour') "
         "AND size_unit IN ('g', 'ml') GROUP BY vendor, currency, size_unit",
         "Looked at: laban at Spinneys and Carrefour, per 100 g or ml, all dates"),
        ("SELECT currency, SUM(line_total) AS total_spent FROM purchases "
         "WHERE item_name = 'bread' AND receipt_date = CURRENT_DATE - 1 GROUP BY currency",
         "Looked at: bread, 2 November 2026"),
        ("SELECT currency, SUM(line_total) AS total_spent FROM purchases "
         "WHERE item_name = 'coffee' AND brand = 'brazilian' GROUP BY currency",
         "Looked at: coffee (brand brazilian), all dates"),
        ("SELECT currency, SUM(total) AS total_spent FROM receipts "
         "WHERE receipt_date > CURRENT_DATE - 7 AND receipt_date <= CURRENT_DATE GROUP BY currency",
         "Looked at: all your spending, 28 October – 3 November 2026"),
        ("WITH spent AS (SELECT SUM(total) AS total FROM receipts) SELECT total FROM spent", None),
    ],
)  # fmt: skip
def test_what_the_query_looked_at(sql, understood):
    assert rules.describe(rules.prepare(guard.check(sql), NAMES_TOO, TODAY)) == understood
