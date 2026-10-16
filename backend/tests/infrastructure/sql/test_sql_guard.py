"""The first line of defence for generated SQL. The allowed queries are the examples approved by the user
on 2026-10-15; the refused ones are what an attacker, or a confused model, might produce."""

import pytest
import sqlglot

from app.domain.assistant.errors import UnsafeQuery
from app.infrastructure.sql.sql_guard import SqlGlotGuard

guard = SqlGlotGuard()

APPROVED_EXAMPLES = [
    # "How much did I spend this month?" / "Adde sarafet hal shaher?"
    "SELECT SUM(total_usd) FROM receipts WHERE receipt_date >= date_trunc('month', CURRENT_DATE)",
    # "How much did I spend on groceries in September?"
    """SELECT SUM(amount_usd) FROM category_spending
       WHERE category = 'Groceries' AND receipt_date >= DATE '2026-09-01' AND receipt_date < DATE '2026-10-01'""",
    # "What were my top 3 categories last month?"
    """SELECT category, SUM(amount_usd) AS spent FROM category_spending
       WHERE receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month'
         AND receipt_date < date_trunc('month', CURRENT_DATE)
       GROUP BY category ORDER BY spent DESC LIMIT 3""",
    # "How much did I last pay for laban?"
    """SELECT receipt_date, vendor, item, unit_price, line_total, currency, size_amount, size_unit
       FROM purchases WHERE item_name ILIKE '%laban%' ORDER BY receipt_date DESC LIMIT 1""",
    # "How many times did I go to Spinneys this month?"
    """SELECT COUNT(*) FROM receipts
       WHERE vendor ILIKE '%spinneys%' AND receipt_date >= date_trunc('month', CURRENT_DATE)""",
]

OTHER_ALLOWED = [
    "SELECT * FROM assistant.receipts",  # the schema written out
    "WITH m AS (SELECT category, SUM(amount_usd) AS s FROM category_spending GROUP BY category) SELECT * FROM m",
    "SELECT vendor FROM receipts UNION SELECT vendor FROM purchases",
    "SELECT EXTRACT(month FROM receipt_date), ROUND(AVG(total_usd), 2), COALESCE(MAX(vendor), '') FROM receipts "
    "GROUP BY 1",
    "SELECT to_char(receipt_date, 'YYYY-MM'), COUNT(DISTINCT vendor) FROM receipts GROUP BY 1",
    "SELECT * FROM receipts r JOIN purchases p ON p.receipt_id = r.receipt_id WHERE r.total > 10",
    "select sum(total) from receipts where currency = 'LBP'",  # lower case
]


LEGITIMATE_CTES = [
    "WITH t AS (SELECT * FROM receipts) SELECT * FROM t",
    "WITH a AS (SELECT * FROM receipts), b AS (SELECT * FROM a) SELECT * FROM b",  # a later CTE uses an earlier one
    "SELECT * FROM (WITH t AS (SELECT * FROM purchases) SELECT * FROM t) s",  # used inside its own subquery
    "WITH t AS (SELECT * FROM receipts) SELECT * FROM t WHERE receipt_id IN (SELECT receipt_id FROM t)",
    "WITH RECURSIVE n AS (SELECT 1 AS i UNION ALL SELECT i + 1 FROM n WHERE i < 3) SELECT * FROM n",
    'WITH "t" AS (SELECT * FROM receipts) SELECT * FROM t',  # quoted lower-case is the same name
    'SELECT * FROM "receipts"',
    "SELECT * FROM receipts r WHERE EXISTS (SELECT 1 FROM purchases p WHERE p.receipt_id = r.receipt_id)",
]


@pytest.mark.parametrize("sql", APPROVED_EXAMPLES + OTHER_ALLOWED + LEGITIMATE_CTES)
def test_allowed_queries_pass(sql):
    checked = guard.check(sql)
    assert checked.upper().startswith(("SELECT", "WITH"))


REFUSED = {
    # changing or creating data
    "delete": "DELETE FROM receipts",
    "update": "UPDATE receipts SET total = 0",
    "insert": "INSERT INTO receipts (total) VALUES (1)",
    "drop": "DROP TABLE receipts",
    "truncate": "TRUNCATE receipts",
    "create": "CREATE TABLE x (a int)",
    "copy": "COPY receipts TO '/tmp/out.csv'",
    "select into": "SELECT * INTO stolen FROM receipts",
    "lock rows": "SELECT * FROM receipts FOR UPDATE",
    "two statements": "SELECT 1 FROM receipts; DELETE FROM receipts",
    "hidden second statement": "SELECT total FROM receipts; SELECT * FROM users",
    "set": "SET app.user_id = '7'",
    # a change hidden inside a SELECT (a "data-modifying CTE")
    "delete inside a select": "WITH gone AS (DELETE FROM receipts RETURNING *) SELECT * FROM gone",
    "update inside a select": "WITH x AS (UPDATE receipts SET total = 0 RETURNING *) SELECT COUNT(*) FROM x",
    "insert inside a select": "WITH x AS (INSERT INTO receipts (total) VALUES (1) RETURNING *) SELECT * FROM x",
    "grant": "GRANT ALL ON receipts TO PUBLIC",
    # reading anything other than the three views
    "users table": "SELECT * FROM users",
    "real receipts table": "SELECT * FROM public.receipts",
    "raw items table": "SELECT * FROM receipt_items",
    "catalog": "SELECT * FROM pg_catalog.pg_tables",
    "catalog unqualified": "SELECT * FROM pg_user",
    "information schema": "SELECT * FROM information_schema.columns",
    "view in another schema": "SELECT * FROM other.receipts",
    "catalog-qualified": "SELECT * FROM expense_tracker.assistant.receipts",
    "subquery on users": "SELECT (SELECT email FROM users LIMIT 1) FROM receipts",
    "join users": "SELECT * FROM receipts JOIN users ON true",
    "function in from": "SELECT * FROM generate_series(1, 10)",
    # functions that could change whose rows are visible, read files, or hang the database
    "set_config": "SELECT set_config('app.user_id', '7', true), * FROM receipts",
    "current_setting": "SELECT current_setting('app.user_id') FROM receipts",
    "pg_sleep": "SELECT pg_sleep(10) FROM receipts",
    "read a file": "SELECT pg_read_file('/etc/passwd') FROM receipts",
    "version": "SELECT version() FROM receipts",
    "dblink": "SELECT * FROM receipts WHERE dblink_exec('x', 'DELETE FROM receipts') = 'x'",
    # a CTE name used where it is not in scope, so the database would read the real table
    # (the first one is the exact query from the 2026-10-15 code review)
    "nested cte leaks out": (
        "WITH x AS (WITH pg_class AS (SELECT 1) SELECT * FROM pg_class) SELECT relname FROM pg_class"
    ),
    "nested cte leaks out, users": "WITH x AS (WITH users AS (SELECT 1) SELECT * FROM users) SELECT * FROM users",
    "sibling cte's inner name": (
        "WITH a AS (SELECT 1), b AS (WITH pg_roles AS (SELECT 1) SELECT 1) SELECT * FROM pg_roles"
    ),
    "subquery cte used outside": "SELECT * FROM (WITH pg_class AS (SELECT 1) SELECT * FROM pg_class) s, pg_class",
    "later cte used too early": "WITH a AS (SELECT * FROM pg_class), pg_class AS (SELECT 1) SELECT * FROM a",
    "cte defined in a where subquery": "SELECT * FROM pg_class WHERE EXISTS (WITH pg_class AS (SELECT 1) SELECT 1)",
    "quoted name is a different name": 'WITH "PG_CLASS" AS (SELECT 1) SELECT * FROM pg_class',
    "quoted view name in wrong case": 'SELECT * FROM "Receipts"',
    # not SQL at all
    "garbage": "how much did I spend",
    "empty": "",
}


@pytest.mark.parametrize("sql", REFUSED.values(), ids=REFUSED.keys())
def test_unsafe_queries_are_refused(sql):
    with pytest.raises(UnsafeQuery):
        guard.check(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT total FROM receipts /* ; DELETE FROM receipts */",
        "SELECT total FROM receipts -- ; DELETE FROM receipts",
        "SELECT total FROM receipts WHERE vendor = 'a''; DELETE FROM receipts --'",
    ],
)
def test_comments_and_quote_tricks_stay_harmless(sql):
    # What comes back is rebuilt from the parsed query: still exactly one SELECT, so checking it
    # again gives the same text, and the would-be DELETE is only inside a comment or a string.
    checked = guard.check(sql)
    assert guard.check(checked) == checked
    assert len(sqlglot.parse(checked, read="postgres")) == 1


def test_what_runs_is_rebuilt_from_what_was_checked():
    assert guard.check("select total from receipts") == "SELECT total FROM receipts"
