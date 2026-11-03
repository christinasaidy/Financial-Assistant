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
