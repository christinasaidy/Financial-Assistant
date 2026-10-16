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
        "and", "or", "exists",
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

        for table in tree.find_all(exp.Table):
            name = _name(table.this)
            schema = _name(table.args.get("db")) if table.args.get("db") else ""
            if name is None or schema is None or table.catalog:
                raise UnsafeQuery("Only the receipts, purchases and category_spending views can be queried")
            if not schema and _refers_to_cte(table, name):
                continue
            if name in VIEWS and schema in ("", VIEW_SCHEMA):
                continue
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


def _name(identifier: exp.Expression | None) -> str | None:
    """A name as PostgreSQL sees it: unquoted names are lower-cased, quoted ones are kept exactly
    ("PG_CLASS" in quotes is not pg_class). None if it is not a plain name at all."""
    if not isinstance(identifier, exp.Identifier):
        return None
    return identifier.this if identifier.args.get("quoted") else identifier.this.lower()


def _cte_names(ctes: list[exp.Expression]) -> set[str | None]:
    return {_name(cte.args["alias"].this) if cte.args.get("alias") else None for cte in ctes}


def _refers_to_cte(table: exp.Table, name: str) -> bool:
    """Does this table reference resolve to a CTE, following SQL's scoping rules?

    Walking outwards from the table: a WITH attached to a query is visible inside that query's body;
    inside a WITH, a CTE sees only the CTEs defined before it (or all of them in WITH RECURSIVE).
    A CTE defined inside a nested query is not visible outside it, so an outer `pg_class` next to an
    inner CTE called pg_class is the real catalog table (found in the 2026-10-15 code review).
    """
    child, node = table, table.parent
    while node is not None:
        if isinstance(node, exp.With):
            ctes = list(node.expressions)
            position = next((i for i, cte in enumerate(ctes) if cte is child), len(ctes))
            visible = ctes if node.args.get("recursive") else ctes[:position]
            if name in _cte_names(visible):
                return True
        else:
            attached = node.args.get("with_") or node.args.get("with")
            if attached is not None and attached is not child and name in _cte_names(list(attached.expressions)):
                return True
        child, node = node, node.parent
    return False
