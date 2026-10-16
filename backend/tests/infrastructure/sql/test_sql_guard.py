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


# --- Second code review (2026-10-16), finding 4: what a value may be cast to ---
# Catalog reference types (regclass, regrole, regprocedure, ...) look a database object up by name: they identify
# objects without reading a table. They do not by themselves run set_config or reach other users' rows, but they are
# outside what a spending question needs, so only ordinary scalar types are allowed.

ALLOWED_CASTS = [
    "SELECT CAST(total AS numeric(10, 2)) FROM receipts",  # precision and scale
    "SELECT total::numeric FROM receipts",
    "SELECT total::decimal(18, 2) FROM receipts",
    "SELECT total::int, total::integer, total::bigint, total::smallint FROM receipts",
    "SELECT total::float, total::real, total::double precision FROM receipts",
    "SELECT vendor::text, vendor::varchar(20), vendor::char(3) FROM receipts",
    "SELECT receipt_date::timestamp, receipt_date::timestamptz, receipt_date::timestamp(0) FROM receipts",
    "SELECT receipt_date::date, '12:00'::time, '1 month'::interval, (total > 1)::boolean FROM receipts",
    "SELECT SUM(total_usd) FROM receipts WHERE receipt_date >= DATE '2026-09-01'",  # a typed literal is a cast too
    "SELECT CAST(CAST(total AS text) AS numeric(10, 2)) FROM receipts",  # nested, both ordinary
    'SELECT CAST(total AS "numeric") FROM receipts',
]


@pytest.mark.parametrize("sql", ALLOWED_CASTS)
def test_ordinary_casts_are_allowed(sql):
    guard.check(sql)


REFUSED_CASTS = {
    # The review's examples.
    "regclass": "SELECT CAST('public.users' AS regclass)",
    "regrole then oid": "SELECT CAST('ai_readonly' AS regrole)::oid",
    "qualified regclass": "SELECT CAST('public.users' AS pg_catalog.regclass)",
    "regprocedure": "SELECT CAST('pg_catalog.set_config(text,text,boolean)' AS regprocedure)::oid",
    # The same with :: and typed-literal syntax, and other catalog reference types.
    ":: regclass": "SELECT 'public.users'::regclass FROM receipts",
    "typed literal": "SELECT regclass 'public.users'",
    "quoted regclass": 'SELECT CAST(\'users\' AS "regclass")',
    "regtype": "SELECT 'int'::regtype",
    "regproc": "SELECT 'now'::regproc",
    "regnamespace": "SELECT 'public'::regnamespace",
    "oid": "SELECT total::oid FROM receipts",
    # Nested: an ordinary outer cast does not hide the inner one.
    "nested inside": "SELECT CAST(CAST('users' AS regclass) AS text)",
    "nested ::": "SELECT 'users'::regclass::text::varchar(10)",
    "inside an aggregate filter": "SELECT COUNT(*) FILTER (WHERE vendor::regclass IS NULL) FROM receipts",
    "inside where": "SELECT * FROM receipts WHERE vendor = 'users'::regclass::text",
    # Schema-qualified, user-defined, pseudo and other unneeded types.
    "qualified ordinary type": "SELECT total::pg_catalog.int4 FROM receipts",
    "other schema": "SELECT vendor::public.mytype FROM receipts",
    "information schema type": "SELECT vendor::information_schema.sql_identifier FROM receipts",
    "user-defined": "SELECT CAST(vendor AS my_type) FROM receipts",
    "record": "SELECT vendor::record FROM receipts",
    "quoted char": 'SELECT vendor::"char" FROM receipts',
    "json": "SELECT vendor::json FROM receipts",
    "name": "SELECT vendor::name FROM receipts",
    "xml": "SELECT vendor::xml FROM receipts",
    "money": "SELECT total::money FROM receipts",
    # Arrays are not needed for spending questions (decision 2026-10-16).
    "array": "SELECT total::int[] FROM receipts",
    "date array": "SELECT receipt_date::date[] FROM receipts",
    # Modifiers only as plain numbers, and only on types that take them.
    "modifier that is not a number": "SELECT vendor::varchar(a) FROM receipts",
    "modifier on a type without one": "SELECT total::int(4) FROM receipts",
    "too many modifiers": "SELECT vendor::varchar(1, 2) FROM receipts",
    "interval fields": "SELECT vendor::interval day to second FROM receipts",
}


@pytest.mark.parametrize("sql", REFUSED_CASTS.values(), ids=REFUSED_CASTS.keys())
def test_casts_to_other_types_are_refused(sql):
    with pytest.raises(UnsafeQuery, match="type"):
        guard.check(sql)


# --- Second code review, finding 5: a function is identified by its schema too, not just its last name part ---
# Only unqualified built-ins are allowed; with search_path = assistant they resolve to pg_catalog. Writing a schema is
# refused for every function, pg_catalog included: no spending question needs it, and one rule is easier to check.

ALLOWED_FUNCTION_CALLS = [
    "SELECT to_char(receipt_date, 'YYYY') FROM receipts",
    "SELECT initcap(vendor) FROM receipts",  # was refused: sqlglot 30 parses it as its own expression type
    "SELECT date_part('year', receipt_date) FROM receipts",
    "SELECT lower(vendor), upper(vendor), trim(vendor), length(vendor) FROM receipts",
    'SELECT "lower"(vendor) FROM receipts',  # quoted lower case is the same name in PostgreSQL
    "SELECT round(avg(total), 2), coalesce(max(vendor), '') FROM receipts",
]


@pytest.mark.parametrize("sql", ALLOWED_FUNCTION_CALLS)
def test_unqualified_built_in_functions_are_allowed(sql):
    guard.check(sql)


REFUSED_FUNCTION_CALLS = {
    # The review's examples.
    "public to_char": "SELECT public.to_char(CURRENT_DATE, 'YYYY')",
    "other initcap": "SELECT other.initcap('x')",
    # Other schemas and positions.
    "assistant schema": "SELECT assistant.lower(vendor) FROM receipts",
    "pg_catalog too": "SELECT pg_catalog.lower(vendor) FROM receipts",
    "pg_catalog date_part": "SELECT pg_catalog.date_part('year', receipt_date) FROM receipts",
    "three parts": "SELECT a.b.lower(vendor) FROM receipts",
    "qualified aggregate": "SELECT public.sum(total) FROM receipts",
    "quoted schema": 'SELECT "public".lower(vendor) FROM receipts',
    "in where": "SELECT * FROM receipts WHERE public.lower(vendor) = 'x'",
    "in order by": "SELECT * FROM receipts ORDER BY other.initcap(vendor)",
    "nested in an allowed call": "SELECT lower(public.upper(vendor)) FROM receipts",
    # A quoted name is case-sensitive in PostgreSQL ("MyFunc" is not myfunc), and sqlglot would rebuild it as "MYFUNC",
    # a different name again; so a quoted name that is not a known built-in is refused.
    "quoted unknown": 'SELECT "MyFunc"(vendor) FROM receipts',
    "quoted unknown, lower case": 'SELECT "myfunc"(vendor) FROM receipts',
    # Still refused, qualified or not.
    "set_config": "SELECT set_config('app.user_id', '7', true)",
    "qualified set_config": "SELECT pg_catalog.set_config('app.user_id', '7', true)",
    "current_setting": "SELECT current_setting('app.user_id')",
    "qualified current_setting": "SELECT pg_catalog.current_setting('app.user_id')",
    "pg_sleep": "SELECT pg_sleep(1)",
    "qualified pg_sleep": "SELECT pg_catalog.pg_sleep(1)",
}


@pytest.mark.parametrize("sql", REFUSED_FUNCTION_CALLS.values(), ids=REFUSED_FUNCTION_CALLS.keys())
def test_qualified_and_unknown_functions_are_refused(sql):
    with pytest.raises(UnsafeQuery):
        guard.check(sql)


def test_the_cte_scope_rule_still_holds_alongside_the_new_checks():
    with pytest.raises(UnsafeQuery):
        guard.check("WITH x AS (WITH pg_class AS (SELECT 1) SELECT * FROM pg_class) SELECT relname::text FROM pg_class")
    guard.check("WITH t AS (SELECT total::numeric(10, 2) AS t FROM receipts) SELECT initcap(t::text) FROM t")
