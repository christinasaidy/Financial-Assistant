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

And it checks the dates against what was asked (approved 2026-11-14, after the fine-tuned model invented periods):
- only yesterday, when neither the question nor an earlier one names it (a yesterday word, its weekday or its day);
- last year's month, when this year's has already come and no year was mentioned ("October" is the most recent one).

And, for a price comparison between named shops whose result misses one of them, it finds the size kinds the item has
at every one of those shops, so the comparison can be repaired with one the SQL left out (approved 2026-11-14: the
fine-tuned model compared "without a size" items that every shop sells by weight, and found nothing).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.application.assistant.dtos import QueryResult
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
# The words for yesterday, the weekdays and a year, as the research dataset spells them (research/dataset/periods.py).
_YESTERDAY_WORDS = ("yesterday", "mbere7", "mberi7", "mbereh", "embere7", "mberha", "mberh")
_WEEKDAY_WORDS = (
    ("monday", "tanayn", "tanain", "tnen", "tnein", "etnen"), ("tuesday", "taleta", "tleeta", "tleta"),
    ("wednesday", "erb3a", "orb3a", "erbaa", "arbi3a"), ("thursday", "khamis", "5amis", "khamees"),
    ("friday", "nhar el jem3a", "yom el jem3a", "jom3a"), ("saturday", "sabet", "sebet", "sabt"),
    ("sunday", "a7ad", "ahad"),
)  # fmt: skip
_YEAR_WORDS = ("year", "years", "sene", "sana")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December")  # fmt: skip
# The size kinds a price comparison can use, in the order a repair suggests them, and what it says for each.
_SIZE_COLUMNS = frozenset({"size_unit", "size_amount"})
_SIZE_KIND = ("CASE WHEN size_unit IN ('g', 'ml') THEN 'g/ml' WHEN size_unit = 'pcs' THEN 'pcs' "
              "WHEN size_amount IS NULL THEN 'none' END")  # fmt: skip
_SIZE_HINTS = {
    "g/ml": ("has sizes in g or ml", "compare per 100 g or ml, with size_unit IN ('g', 'ml') and the price / "
                                     "size_amount * 100"),
    "pcs": ("has sizes in pieces", "compare per piece, with size_unit = 'pcs' and the price / size_amount"),
    "none": ("has no sizes", "compare per unit, with size_amount IS NULL"),
}  # fmt: skip


@dataclass(frozen=True)
class _Comparison:
    item: str
    vendors: tuple[str, ...]
    used: frozenset[str]  # the size kinds its size conditions let through
    others: tuple[exp.Expression, ...]  # its other conditions (the item, the shops, the period)


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

    def check_dates(self, sql: str, asked: str, today: date) -> None:
        tree = _parse(sql)
        yesterday = today - timedelta(days=1)
        days = {_date_of(node.expression, today) for node in tree.find_all(exp.EQ) if _is_receipt_date(node.this)}
        if yesterday in days and not _names_the_day(asked, yesterday):
            raise QueryRejected(
                "The question does not mention yesterday: use the period it names, or no date filter if it names none"
            )
        starts = {_date_of(node.expression, today) for node in tree.find_all(exp.GTE) if _is_receipt_date(node.this)}
        ends = {_date_of(node.expression, today) for node in tree.find_all(exp.LT) if _is_receipt_date(node.this)}
        for start in starts:
            if (start and start.day == 1 and _next_month(start) in ends and start.year == today.year - 1
                    and start.month <= today.month and not _mentions_a_year(asked)):  # fmt: skip
                latest = start.replace(year=today.year)
                raise QueryRejected(
                    f"A month named without a year is the most recent one: {_MONTHS[start.month - 1]} is "
                    f"receipt_date >= '{latest}' AND receipt_date < '{_next_month(latest)}'"
                )

    def sizes_query(self, sql: str) -> str | None:
        comparison = _comparison(_parse(sql))
        if comparison is None:
            return None
        query = exp.select("vendor", f"{_SIZE_KIND} AS size_kind").distinct().from_("purchases")
        return query.where(exp.and_(*comparison.others)).sql(dialect="postgres")

    def size_hint(self, sql: str, result: QueryResult, sizes: QueryResult) -> str | None:
        comparison = _comparison(_parse(sql))
        if comparison is None or "vendor" not in result.columns:
            return None
        column = result.columns.index("vendor")
        if {row[column] for row in result.rows} >= set(comparison.vendors):
            return None
        kinds: dict[str, set[str]] = {}
        for vendor, kind in sizes.rows:
            kinds.setdefault(vendor, set()).add(kind)
        common = set.intersection(*(kinds.get(vendor, set()) for vendor in comparison.vendors))
        for kind in _SIZE_HINTS:
            if kind in common and kind not in comparison.used:
                has, how = _SIZE_HINTS[kind]
                return f"{comparison.item} {has} at {_all_of(comparison.vendors)}: {how}"
        return None

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


def _is_receipt_date(node: exp.Expression) -> bool:
    return isinstance(node, exp.Column) and node.name == "receipt_date"


def _date_of(node: exp.Expression, today: date) -> date | None:
    """The date a simple date expression stands for ('2026-11-02', CAST(... AS DATE), CURRENT_DATE, minus days)."""
    if isinstance(node, exp.CurrentDate):
        return today
    if isinstance(node, exp.Cast):
        return _date_of(node.this, today)
    if isinstance(node, exp.Literal) and node.is_string:
        try:
            return date.fromisoformat(node.this)
        except ValueError:
            return None
    if isinstance(node, exp.Sub) and isinstance(node.expression, exp.Literal) and not node.expression.is_string:
        day = _date_of(node.this, today)
        return day - timedelta(days=int(node.expression.this)) if day and node.expression.this.isdigit() else None
    return None


def _next_month(day: date) -> date:
    return date(day.year + day.month // 12, day.month % 12 + 1, 1)


def _mentions(text: str, word: str) -> bool:
    """A whole word or phrase (Arabizi digits count as letters: 'erb3a', 'a7ad')."""
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text.lower()) is not None


def _names_the_day(asked: str, day: date) -> bool:
    words = _YESTERDAY_WORDS + _WEEKDAY_WORDS[day.weekday()] + (str(day.day), day.isoformat())
    return any(_mentions(asked, word) for word in words)


def _mentions_a_year(asked: str) -> bool:
    return re.search(r"(?<!\d)(19|20)\d\d(?!\d)", asked) is not None or any(_mentions(asked, w) for w in _YEAR_WORDS)


def _comparison(tree: exp.Expression) -> _Comparison | None:
    """A price comparison of one item between named shops in purchases, or None."""
    if not isinstance(tree, exp.Select) or tree.args.get("with_") or tree.args.get("with") or tree.args.get("joins"):
        return None
    if tree.args.get("limit") or tree.args.get("having"):  # it may leave a shop out on purpose ("only the cheapest")
        return None
    source = tree.args.get("from_") or tree.args.get("from")
    where = tree.args.get("where")
    if source is None or not isinstance(source.this, exp.Table) or source.this.name != "purchases" or where is None:
        return None
    conditions = list(where.this.flatten()) if isinstance(where.this, exp.And) else [where.this]
    item, vendors, used, others = None, (), {"g/ml", "pcs", "none"}, []
    for condition in conditions:
        columns = {column.name for column in condition.find_all(exp.Column)}
        if columns & _SIZE_COLUMNS:
            used &= _size_kinds(condition)
            continue
        others.append(condition)
        if isinstance(condition, exp.EQ) and _is_column(condition.this, "item_name") and _is_text(condition.expression):
            item = condition.expression.this
        if isinstance(condition, exp.In) and _is_column(condition.this, "vendor"):
            if all(_is_text(value) for value in condition.expressions):
                vendors = tuple(value.this for value in condition.expressions)
    if item is None or len(vendors) < 2:
        return None
    return _Comparison(item, vendors, frozenset(used), tuple(others))


def _size_kinds(condition: exp.Expression) -> set[str]:
    """The size kinds a size condition lets through; all of them when it is not one of the usual shapes."""
    if isinstance(condition, exp.Is) and _is_column(condition.this, "size_amount"):
        return {"none"}
    if isinstance(condition, exp.Not) and isinstance(condition.this, exp.Is):
        return {"g/ml", "pcs"} if _is_column(condition.this.this, "size_amount") else {"g/ml", "pcs", "none"}
    if isinstance(condition, (exp.EQ, exp.In)) and _is_column(condition.this, "size_unit"):
        units = [condition.expression] if isinstance(condition, exp.EQ) else condition.expressions
        values = {value.this for value in units if _is_text(value)}
        return {"g/ml"} if values and values <= {"g", "ml"} else {"pcs"} if values == {"pcs"} else {"g/ml", "pcs", "none"}
    return {"g/ml", "pcs", "none"}


def _is_column(node: exp.Expression, name: str) -> bool:
    return isinstance(node, exp.Column) and node.name == name


def _is_text(node: exp.Expression) -> bool:
    return isinstance(node, exp.Literal) and node.is_string


def _all_of(vendors: Sequence[str]) -> str:
    if len(vendors) == 2:
        return f"both {vendors[0]} and {vendors[1]}"
    return f"all of {', '.join(vendors[:-1])} and {vendors[-1]}"


def _is_aggregate(tree: exp.Select) -> bool:
    if tree.args.get("group") or tree.args.get("having") or tree.args.get("distinct"):
        return True
    return any(
        projection.find(exp.AggFunc) is not None or projection.find(exp.Window) is not None
        for projection in tree.expressions
    )
