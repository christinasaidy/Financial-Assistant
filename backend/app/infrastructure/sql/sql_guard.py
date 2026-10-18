"""The first line of defence for generated SQL (the read-only database role is the second).

A query may run only if it is one SELECT (CTEs and UNIONs of SELECTs allowed), reads only the three
assistant views, and calls only functions on the allowed list. Everything else is refused, including
`set_config` / `current_setting` (which could change whose rows are visible), `pg_sleep`, file and
catalog access. What runs is the SQL rebuilt from the checked tree, never the original text, so the
database runs exactly what was checked.

Size (third code review, 2026-10-18): the checker also refuses what could manufacture large amounts of data without
reading any receipt: SQL text over MAX_SQL_LENGTH (refused before parsing), recursive CTEs (the one construct that
generates unbounded rows or values from nothing), and type sizes above MODIFIER_LIMITS (char(10000000) pads every
value to 10 MB). These act before the query runs. The runner adds the limits that need the database: time, rows,
columns, and the size of the result it keeps (see readonly_query_runner.py).
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
        "lower", "upper", "trim", "length", "concat", "initcap",
        "extract", "cast", "trycast", "timestamptrunc", "datetrunc", "timetostr",
        "currentdate", "currenttimestamp",
    }
)  # fmt: skip
# Functions sqlglot does not know, written as they are in PostgreSQL (sqlglot 30 knows all three; kept in case
# another version does not).
ALLOWED_OTHER_FUNCTIONS = frozenset({"date_part", "to_char", "initcap"})

# Types a value may be cast to: the ordinary scalar types spending questions need. Everything else is refused,
# notably catalog reference types (regclass, regrole, regprocedure, oid, ...), which look database objects up by
# name, and user-defined, schema-qualified and array types (second code review, 2026-10-16).
_Type = exp.DataType.Type
ALLOWED_TYPES = frozenset(
    {
        _Type.SMALLINT, _Type.INT, _Type.BIGINT, _Type.DECIMAL, _Type.FLOAT, _Type.DOUBLE,
        _Type.TEXT, _Type.VARCHAR, _Type.CHAR, _Type.BOOLEAN,
        _Type.DATE, _Type.TIME, _Type.TIMESTAMP, _Type.TIMESTAMPTZ, _Type.INTERVAL,
    }
)  # fmt: skip
# How many size modifiers a type may have: numeric(precision, scale), varchar(n), char(n), timestamp(precision).
_MAX_MODIFIERS = {
    _Type.DECIMAL: 2, _Type.VARCHAR: 1, _Type.CHAR: 1, _Type.TIME: 1, _Type.TIMESTAMP: 1, _Type.TIMESTAMPTZ: 1,
}  # fmt: skip
# The allowed range of each modifier. Text lengths stay small (char pads every value to its length; vendor and item
# names are short); numeric precision up to 38 covers every stored amount (NUMERIC(18, 2), rates NUMERIC(18, 6));
# fractional seconds go up to PostgreSQL's own maximum of 6. A numeric scale may not exceed its precision.
MAX_TEXT_LENGTH = 255
MAX_NUMERIC_PRECISION = 38
MAX_SECONDS_PRECISION = 6
MODIFIER_LIMITS = {
    _Type.VARCHAR: (1, MAX_TEXT_LENGTH), _Type.CHAR: (1, MAX_TEXT_LENGTH), _Type.DECIMAL: (1, MAX_NUMERIC_PRECISION),
    _Type.TIME: (0, MAX_SECONDS_PRECISION), _Type.TIMESTAMP: (0, MAX_SECONDS_PRECISION),
    _Type.TIMESTAMPTZ: (0, MAX_SECONDS_PRECISION),
}  # fmt: skip
MAX_SQL_LENGTH = 10_000  # characters; a question's SQL is a few hundred

_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
    exp.Command, exp.Copy, exp.Set, exp.Transaction, exp.Commit, exp.Rollback, exp.Grant,
)  # fmt: skip


class SqlGlotGuard:
    def check(self, sql: str) -> str:
        if len(sql) > MAX_SQL_LENGTH:  # before parsing, so an enormous text costs nothing
            raise UnsafeQuery(f"The query is too long (more than {MAX_SQL_LENGTH} characters)")
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
            if isinstance(node, exp.With) and node.args.get("recursive"):
                raise UnsafeQuery("Recursive queries are not allowed")

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
            # `public.to_char(...)` is a function in another schema, not the built-in: refuse any schema, so a call
            # always resolves to pg_catalog (the search path is only `assistant`, which defines no functions).
            if isinstance(function.parent, exp.Dot) and function.arg_key == "expression":
                raise UnsafeQuery("Functions cannot be called with a schema name")
            if isinstance(function, exp.Case):
                # CASE is an expression, not a call; what is inside it is checked like everything else.
                allowed = True
            elif isinstance(function, exp.If):
                # sqlglot represents each WHEN ... THEN of a CASE as an If. Only that: a bare IF(a, b, c) or IIF(),
                # which PostgreSQL does not have, also parses to If and would be silently rebuilt as a CASE.
                allowed = isinstance(function.parent, exp.Case) and function.arg_key == "ifs"
            elif isinstance(function, exp.Anonymous):
                # A quoted name is case-sensitive ("MyFunc" is not myfunc) and sqlglot does not rebuild it faithfully,
                # so only plain, unquoted names count as the built-ins on the list.
                allowed = isinstance(function.this, str) and function.this.lower() in ALLOWED_OTHER_FUNCTIONS
            else:
                allowed = function.key in ALLOWED_FUNCTIONS
            if not allowed:
                name = function.name if isinstance(function, exp.Anonymous) else function.key
                raise UnsafeQuery(f"The function {name} is not allowed")

        # Every type written in the query: cast targets (CAST, ::, typed literals) and anything nested inside them.
        for cast in tree.find_all(exp.Cast):
            _check_type(cast.args.get("to"))
        for node in tree.find_all(exp.DataType, exp.ObjectIdentifier, exp.PseudoType):
            _check_type(node)

        return tree.sql(dialect="postgres")


def _check_type(node: exp.Expression | None) -> None:
    """An allowed scalar type, with at most the size modifiers it takes, each a plain number."""
    if (
        type(node) is exp.DataType  # not ObjectIdentifier (regclass, oid, ...) or another subclass
        and node.this in ALLOWED_TYPES
        and len(node.expressions) <= _MAX_MODIFIERS.get(node.this, 0)
        and all(_is_size(modifier) for modifier in node.expressions)
    ):
        _check_modifier_sizes(node)
        return
    raise UnsafeQuery("Casting to this type is not allowed")


def _check_modifier_sizes(node: exp.DataType) -> None:
    sizes = [int(modifier.this.this) for modifier in node.expressions]
    if not sizes:
        return
    low, high = MODIFIER_LIMITS[node.this]
    scale_too_big = node.this is _Type.DECIMAL and len(sizes) == 2 and sizes[1] > sizes[0]
    if not low <= sizes[0] <= high or scale_too_big:
        raise UnsafeQuery(f"This type size is not allowed (allowed: {low} to {high})")


def _is_size(modifier: exp.Expression) -> bool:
    value = modifier.this if isinstance(modifier, exp.DataTypeParam) else None
    return isinstance(value, exp.Literal) and not value.is_string and str(value.this).isdigit()


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
