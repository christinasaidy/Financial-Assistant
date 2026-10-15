"""The first line of defence for generated SQL (the read-only database role is the second).

A query may run only if it is one SELECT (CTEs and UNIONs of SELECTs allowed), reads only the three
assistant views, and calls only functions on the allowed list. Everything else is refused, including
`set_config` / `current_setting` (which could change whose rows are visible), `pg_sleep`, file and
catalog access. What runs is the SQL rebuilt from the checked tree, never the original text, so the
database runs exactly what was checked.
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.domain.assistant.errors import UnsafeQuery

VIEWS = frozenset({"receipts", "purchases", "category_spending"})
VIEW_SCHEMA = "assistant"

# sqlglot's names for the built-in functions it understands (plus AND/OR, which it also treats as functions).
ALLOWED_FUNCTIONS = frozenset(
    {
        "and", "or",
        "sum", "count", "avg", "min", "max",
        "round", "abs", "coalesce", "nullif", "greatest", "least",
        "lower", "upper", "trim", "length", "concat",
        "extract", "cast", "trycast", "timestamptrunc", "datetrunc", "timetostr",
        "currentdate", "currenttimestamp",
    }
)  # fmt: skip
# Functions sqlglot does not know, written as they are in PostgreSQL.
ALLOWED_OTHER_FUNCTIONS = frozenset({"date_part", "to_char", "initcap"})

_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
    exp.Command, exp.Copy, exp.Set, exp.Transaction, exp.Commit, exp.Rollback, exp.Grant,
)  # fmt: skip


class SqlGlotGuard:
    def check(self, sql: str) -> str:
        try:
            statements = [statement for statement in sqlglot.parse(sql, read="postgres") if statement is not None]
        except SqlglotError as exc:
            raise UnsafeQuery("This is not valid SQL") from exc
        if len(statements) != 1:
            raise UnsafeQuery("Only one statement is allowed")
        tree = statements[0]

        if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
            raise UnsafeQuery("Only SELECT queries are allowed")
        for node in tree.walk():
            if isinstance(node, _FORBIDDEN_NODES):
                raise UnsafeQuery("Only SELECT queries are allowed")
            if isinstance(node, exp.Select) and (node.args.get("into") or node.args.get("locks")):
                raise UnsafeQuery("SELECT INTO and row locking are not allowed")

        cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
        for table in tree.find_all(exp.Table):
            name, schema = table.name.lower(), table.db.lower()
            allowed_view = name in VIEWS and schema in ("", VIEW_SCHEMA) and not table.catalog
            allowed_cte = name in cte_names and not schema and not table.catalog
            if not (allowed_view or allowed_cte):
                raise UnsafeQuery("Only the receipts, purchases and category_spending views can be queried")

        for function in tree.find_all(exp.Func):
            if isinstance(function, exp.Anonymous):
                allowed = function.name.lower() in ALLOWED_OTHER_FUNCTIONS
            else:
                allowed = function.key in ALLOWED_FUNCTIONS
            if not allowed:
                name = function.name if isinstance(function, exp.Anonymous) else function.key
                raise UnsafeQuery(f"The function {name} is not allowed")

        return tree.sql(dialect="postgres")
