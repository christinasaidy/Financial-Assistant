"""The answering rules for generated SQL (assistant phase 3, approved by the user on 2026-11-03).

The guard (sql_guard.py) decides whether SQL is safe to run. These rules decide whether safe SQL answers the
question the way it must, and are kept apart so the guard's own job and tests stay as they were:
- names match exactly: no LIKE, ILIKE, SIMILAR TO or regular expressions on item, item_name, vendor or category
  ("water" must not find "water heater"), and a name compared with item_name, vendor or category must be one of
  the user's names given in the prompt. The second rule turns a made-up name into a clarifying question instead of
  an empty answer. Known limitation: only the names in the prompt count (at most 200 items, 100 vendors), so a
  very old item of a user with many items is refused;
- the date: the model writes CURRENT_DATE, which is replaced here by a fixed date (Beirut's today in the app, a set
  date in evaluation), so the saved SQL shows the date it used and can be run again with the same result. Reading
  the clock any other way (now(), CURRENT_TIMESTAMP, 'today'::date, ...) is refused, since receipts only have dates.

It also builds the query for the receipts an answer is based on ("based on N receipts").
"""

from datetime import date

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.domain.assistant.errors import QueryRejected
from app.domain.assistant.prompt import UserNames

_LOOSE_MATCHES = (exp.Like, exp.ILike, exp.SimilarTo, exp.RegexpLike, exp.RegexpILike)
_CLOCK = (exp.CurrentTimestamp, exp.CurrentTime, exp.CurrentDatetime, exp.Localtime, exp.Localtimestamp)
_CLOCK_WORDS = frozenset({"now", "today", "tomorrow", "yesterday"})  # PostgreSQL reads these as the server's clock
# The name columns, the list of the user's names each must come from, and how they are called in messages.
_NAME_COLUMNS = {"item_name": "items", "vendor": "vendors", "category": "categories"}
_LABELS = {"item": "Item", "item_name": "Item", "vendor": "Vendor", "category": "Category"}
_EXACT_COLUMN = {"item": "item_name", "item_name": "item_name", "vendor": "vendor", "category": "category"}
# Queries that list rows keep their order and limit, so the sources are exactly the rows shown.
_SOURCE_ALIAS = "source_receipt_id"


class SqlGlotQueryRules:
    def prepare(self, sql: str, names: UserNames, today: date) -> str:
        tree = _parse(sql)
        _check_exact_names(tree, names)
        _check_no_clock(tree)
        dated = tree.transform(
            lambda node: exp.cast(exp.Literal.string(today.isoformat()), exp.DataType.Type.DATE)
            if isinstance(node, exp.CurrentDate)
            else node
        )
        return dated.sql(dialect="postgres")

    def sources_query(self, sql: str) -> str | None:
        tree = _parse(sql)
        if not isinstance(tree, exp.Select) or tree.args.get("with_") or tree.args.get("with"):
            return None
        source = (tree.args.get("from_") or tree.args.get("from"))
        if source is None or not isinstance(source.this, exp.Table):
            return None
        if any(not isinstance(join.this, exp.Table) for join in tree.args.get("joins") or []):
            return None
        receipt_id = exp.column("receipt_id", table=source.this.alias_or_name)

        if _is_aggregate(tree):
            # One row stands for many purchases: the sources are every row the filters matched (HAVING and LIMIT
            # are dropped, so for "top 3" this is wider than the rows shown; a known limitation).
            query = tree.copy()
            for key in ("group", "having", "order", "limit", "offset", "qualify", "distinct"):
                query.set(key, None)
            query.set("expressions", [receipt_id.as_("receipt_id")])
            query.set("distinct", exp.Distinct())
            return query.order_by("1").sql(dialect="postgres")

        # Each row is one purchase or receipt: keep the order and limit, so the sources are the rows shown.
        shown = tree.copy().select(receipt_id.as_(_SOURCE_ALIAS))
        query = exp.select(exp.column(_SOURCE_ALIAS)).distinct().from_(shown.subquery("shown")).order_by("1")
        return query.sql(dialect="postgres")


def _parse(sql: str) -> exp.Expression:
    try:
        return sqlglot.parse_one(sql, read="postgres")
    except SqlglotError as exc:
        raise QueryRejected("This is not valid SQL") from exc


def _check_exact_names(tree: exp.Expression, names: UserNames) -> None:
    for match in tree.find_all(*_LOOSE_MATCHES):
        for column in match.find_all(exp.Column):
            if column.name in _LABELS:
                raise QueryRejected(
                    f"{_LABELS[column.name]} names must match exactly: use {_EXACT_COLUMN[column.name]} = '<name>' "
                    "with a name from the list"
                )

    allowed = {"items": names.items, "vendors": names.vendors, "categories": names.categories}
    for comparison in tree.find_all(exp.EQ, exp.NEQ, exp.In):
        sides = [comparison.this, *comparison.expressions] if isinstance(comparison, exp.In) else [
            comparison.this, comparison.expression]  # fmt: skip
        named = [side for side in sides if isinstance(side, exp.Column) and side.name in _NAME_COLUMNS]
        wrapped = [side for side in sides if not isinstance(side, exp.Column) and _has_name_column(side)]
        if wrapped:
            # lower(vendor) = 'spinneys' would get past the name list below, so names are compared as they are.
            column = next(c.name for side in wrapped for c in side.find_all(exp.Column) if c.name in _NAME_COLUMNS)
            raise QueryRejected(f"Compare {column} with a name exactly as listed, without functions around it")
        if not named:
            continue
        kind = _NAME_COLUMNS[named[0].name]
        for side in sides:
            if isinstance(side, exp.Literal) and side.is_string and side.this not in allowed[kind]:
                raise QueryRejected(
                    f"'{side.this}' is not one of the user's {kind}: use a name from the list, or reply CLARIFY"
                )


def _has_name_column(node: exp.Expression) -> bool:
    if isinstance(node, (exp.Select, exp.Subquery)):  # a subquery's own columns are checked on their own
        return False
    return any(column.name in _NAME_COLUMNS for column in node.find_all(exp.Column))


def _check_no_clock(tree: exp.Expression) -> None:
    if any(True for _ in tree.find_all(*_CLOCK)):
        raise QueryRejected("Use CURRENT_DATE for dates; now(), CURRENT_TIMESTAMP and similar are not allowed")
    for cast in tree.find_all(exp.Cast):
        value = cast.this
        if isinstance(value, exp.Literal) and value.is_string and value.this.strip().lower() in _CLOCK_WORDS:
            raise QueryRejected(f"Use CURRENT_DATE for dates, not '{value.this}'")


def _is_aggregate(tree: exp.Select) -> bool:
    if tree.args.get("group") or tree.args.get("having") or tree.args.get("distinct"):
        return True
    return any(
        projection.find(exp.AggFunc) is not None or projection.find(exp.Window) is not None
        for projection in tree.expressions
    )
