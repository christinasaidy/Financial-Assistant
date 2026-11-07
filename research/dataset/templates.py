"""The dataset's question templates: for one synthetic user, what is asked, and the SQL that answers it.

Code writes every SQL target, in the shapes the prompt teaches and the user approved (rounds 1-3 on 2026-11-05, the
new templates and periods on 2026-11-07); the question writer (Qwen) only phrases the question from `description`,
and for CLARIFY and REPLY writes the reply. Targets use CURRENT_DATE, as the model must write them; the app fills it in.

A template picks what the user actually bought: its item, shop or category had receipts in the chosen period nine
times in ten; otherwise any of the user's items, so about one answer in ten is empty on purpose (a user can have an
item and still have bought none of it that week, and that is a query, not a CLARIFY).
"""

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date

from research.dataset import periods
from research.dataset.catalogue import Catalogue, Item, Shop
from research.dataset.periods import Period
from research.dataset.users import PlannedLine, PlannedReceipt, SyntheticUser

UNIT_PRICE = "COALESCE(unit_price, line_total / quantity)"
TAX_CATEGORY = "Tax, discounts & rounding"
IN_PERIOD_SHARE = 0.9  # slots taken from what was bought in the period; the rest may give an empty answer


@dataclass(frozen=True)
class Spec:
    """One thing to ask. Qwen writes several phrasings of it; each becomes a training example."""

    template: str
    kind: str  # sql, clarify, unsupported or reply
    description: str  # what the question asks, in plain English, for the question writer
    target: str | None  # the SQL with CURRENT_DATE (sql), "UNSUPPORTED", or None when Qwen writes the reply
    mentions: tuple[tuple[str, ...], ...] = ()  # a question must contain one word of each group
    reply_hint: str | None = None  # for CLARIFY and REPLY: what the reply should say
    base: "Spec | None" = None  # for a follow-up: the earlier question it follows
    labels: dict = field(default_factory=dict)


class UserData:
    """A synthetic user's receipts, seen the way the templates need them."""

    def __init__(self, user: SyntheticUser, catalogue: Catalogue) -> None:
        self.user = user
        self.catalogue = catalogue
        self.today = user.today
        self.first_day = min(r.day for r in user.receipts)
        self.lines: list[tuple[PlannedReceipt, PlannedLine]] = [(r, line) for r in user.receipts for line in r.lines]
        self.items = sorted({line.item for _, line in self.lines})
        self.shops = sorted({r.shop for r in user.receipts})
        self.categories = sorted({r.category for r in user.receipts} | {
            line.category for _, line in self.lines if line.category})  # fmt: skip
        shop_by_name = {shop.name: shop for shop in catalogue.shops}
        self.shop = shop_by_name.__getitem__

    def bought(self, period: Period, item: str | None = None, shop: str | None = None) -> list[PlannedLine]:
        return [line for r, line in self.lines if _within(r.day, period) and (item is None or line.item == item)
                and (shop is None or r.shop == shop)]  # fmt: skip

    def receipts_in(self, period: Period) -> list[PlannedReceipt]:
        return [r for r in self.user.receipts if _within(r.day, period)]


def _within(day: date, period: Period) -> bool:
    return period.start is None or period.start <= day < period.end


# --- SQL helpers ---


def _where(*conditions: str) -> str:
    kept = [c for c in conditions if c]
    return " WHERE " + " AND ".join(kept) if kept else ""


def money(view: str, amount: str, *conditions: str) -> str:
    """An amount per currency with its USD value, as the prompt asks."""
    return (f"SELECT currency, SUM({amount}) AS total_spent, SUM({amount}_usd) AS total_spent_usd FROM {view}"
            f"{_where(*conditions)} GROUP BY currency")  # fmt: skip


def dollars(view: str, amount: str, *conditions: str) -> str:
    return f"SELECT SUM({amount}_usd) AS total_spent_usd FROM {view}{_where(*conditions)}"


def quoted(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def item_is(name: str) -> str:
    return f"item_name = {quoted(name)}"


def items_in(names: Sequence[str]) -> str:
    return "item_name IN (" + ", ".join(quoted(n) for n in names) + ")"


# --- words a question must contain ---


def item_words(item: Item) -> tuple[str, ...]:
    return (item.name,) + item.spellings


def shop_words(shop: Shop) -> tuple[str, ...]:
    return (shop.name,) + shop.nicknames + shop.suggested


def category_words(catalogue: Catalogue, category: str) -> tuple[str, ...]:
    return (category.lower(),) + catalogue.category_words.get(category, ())


# --- picking what to ask about ---


def _pick_item(data: UserData, rng: random.Random, period: Period, allowed: Callable[[Item], bool] = lambda i: True
               ) -> Item | None:  # fmt: skip
    choices = [data.catalogue.item(name) for name in data.items if allowed(data.catalogue.item(name))]
    in_period = [item for item in choices if data.bought(period, item.name)]
    pool = in_period if in_period and rng.random() < IN_PERIOD_SHARE else choices
    return rng.choice(pool) if pool else None


def _pick_shop(data: UserData, rng: random.Random, period: Period) -> Shop | None:
    in_period = sorted({r.shop for r in data.receipts_in(period)})
    pool = in_period if in_period and rng.random() < IN_PERIOD_SHARE else data.shops
    return data.shop(rng.choice(pool)) if pool else None


def _period(data: UserData, rng: random.Random) -> Period:
    """A period in which the user has receipts (tried a few times), so empty answers come mostly from the deliberate
    one in ten, not from asking about a day they bought nothing."""
    for _ in range(10):
        period = periods.choose(rng, data.today, data.first_day)
        if period.start is None or data.receipts_in(period):
            return period
    return period


def _spec(template: str, description: str, target: str, period: Period, *mentions: tuple[str, ...], **labels
          ) -> Spec:  # fmt: skip
    groups = tuple(m for m in mentions if m) + ((period.words,) if period.words else ())
    return Spec(template, "sql", description, target, groups, labels={"period": period.kind, **labels})


# --- the SQL templates ---


def t1_total(data: UserData, rng: random.Random) -> Spec:
    p = _period(data, rng)
    return _spec("T1", f"How much the user spent in total, {p.description}.", money("receipts", "total", p.sql), p)


def t2_total_in_dollars(data: UserData, rng: random.Random) -> Spec:
    p = _period(data, rng)
    return _spec("T2", f"How much the user spent in total in US dollars (they ask for dollars), {p.description}.",
                 dollars("receipts", "total", p.sql), p, ("dollar", "usd", "$", "dollars", "dolar"))  # fmt: skip


def t3_category(data: UserData, rng: random.Random) -> Spec | None:
    p = _period(data, rng)
    if rng.random() < 0.2:
        return _group(data, rng, p)
    shared = [c for c in data.categories if c in data.catalogue.default_categories or c in data.user.private_categories]
    in_period = sorted({r.category for r in data.receipts_in(p)} & set(shared))
    pool = in_period if in_period and rng.random() < IN_PERIOD_SHARE else shared
    category = rng.choice(pool)
    words = category_words(data.catalogue, category)
    return _spec("T3", f"How much the user spent on the category {category}, {p.description}.",
                 money("category_spending", "amount", f"category = {quoted(category)}", p.sql), p, words,
                 category=category)  # fmt: skip


def _group(data: UserData, rng: random.Random, p: Period) -> Spec | None:
    """A kind of product that is not a category (clothes, medicine, ...): the user's items of that kind. A private
    category's own words (dekhan, pets, ...) name the category when the user has it, and its items when not."""
    options = []
    for group, words in data.catalogue.group_words.items():
        names = [n for n in data.items if data.catalogue.item(n).group == group]
        if names and words:
            options.append((group, words, names, None))
    for category in data.catalogue.private_categories:
        names = [n for n in data.items if data.catalogue.item(n).category == category]
        words = data.catalogue.category_words.get(category, ())
        if names and words:
            options.append((category.lower(), words, names, category if category in data.user.private_categories
                            else None))  # fmt: skip
    if not options:
        return None
    group, words, names, category = rng.choice(options)
    if category:
        target = money("category_spending", "amount", f"category = {quoted(category)}", p.sql)
    else:
        target = money("purchases", "line_total", items_in(sorted(names)), p.sql)
    return _spec("T3g", f"How much the user spent on {group} (a kind of product, not a category), {p.description}.",
                 target, p, words, group=group)  # fmt: skip


def t4_where_the_money_went(data: UserData, rng: random.Random) -> Spec:
    p = _period(data, rng)
    target = (f"SELECT category, currency, SUM(amount) AS total_spent, SUM(amount_usd) AS total_spent_usd "
              f"FROM category_spending{_where(p.sql)} GROUP BY category, currency ORDER BY total_spent_usd DESC")
    return _spec("T4", f"Where the user's money went, split by category, {p.description}.", target, p)


def t5_top_categories(data: UserData, rng: random.Random) -> Spec:
    p, n = _period(data, rng), rng.choice([2, 3, 3, 5])
    target = (f"SELECT category, SUM(amount_usd) AS total_spent_usd FROM category_spending"
              f"{_where(f'category <> {quoted(TAX_CATEGORY)}', p.sql)} GROUP BY category "
              f"ORDER BY total_spent_usd DESC LIMIT {n}")  # fmt: skip
    words = {2: ("2", "two", "tnen", "tneen"), 3: ("3", "three", "tlete", "tleteh"), 5: ("5", "five", "khamse")}[n]
    return _spec("T5", f"The {n} categories the user spent the most on, {p.description}.", target, p, words, top=n)


def t6_shop(data: UserData, rng: random.Random) -> Spec | None:
    p = _period(data, rng)
    shop = _pick_shop(data, rng, p)
    return _spec("T6", f"How much the user spent at {shop.name}, {p.description}.",
                 money("receipts", "total", f"vendor = {quoted(shop.name)}", p.sql), p, shop_words(shop),
                 shop=shop.name) if shop else None  # fmt: skip


def t7_top_shop(data: UserData, rng: random.Random) -> Spec:
    p = _period(data, rng)
    target = (f"SELECT vendor, SUM(total_usd) AS total_spent_usd FROM receipts{_where(p.sql)} GROUP BY vendor "
              "ORDER BY total_spent_usd DESC LIMIT 1")
    also = rng.choice(["", ", and how much they spent there"])
    return _spec("T7", f"Which shop the user spent the most at{also}, {p.description}.", target, p)


def t8_visits(data: UserData, rng: random.Random) -> Spec | None:
    p = _period(data, rng)
    shop = _pick_shop(data, rng, p)
    if shop is None:
        return None
    target = f"SELECT COUNT(DISTINCT receipt_id) AS visits FROM receipts{_where(f'vendor = {quoted(shop.name)}', p.sql)}"
    return _spec("T8", f"How many times the user went to {shop.name}, {p.description}.", target, p, shop_words(shop),
                 shop=shop.name)  # fmt: skip


def t9_item(data: UserData, rng: random.Random) -> Spec | None:
    p = _period(data, rng)
    item = _pick_item(data, rng, p)
    return _spec("T9", f"How much the user spent on {item.name} (no brand named), {p.description}.",
                 money("purchases", "line_total", item_is(item.name), p.sql), p, item_words(item),
                 item=item.name) if item else None  # fmt: skip


def t10_brand(data: UserData, rng: random.Random) -> Spec | None:
    p = _period(data, rng)
    branded = sorted({(line.item, line.brand) for _, line in data.lines if line.brand})
    in_period = sorted({(line.item, line.brand) for line in data.bought(p) if line.brand})
    pool = in_period if in_period and rng.random() < IN_PERIOD_SHARE else branded
    if not pool:
        return None
    name, brand = rng.choice(pool)
    item = data.catalogue.item(name)
    target = money("purchases", "line_total", item_is(name), f"brand = {quoted(brand)}", p.sql)
    return _spec("T10", f"How much the user spent on {brand} {name} (the brand {brand} is named), {p.description}.",
                 target, p, item_words(item), _brand_words(item, brand), item=name, brand=brand)  # fmt: skip


def _brand_words(item: Item, brand: str) -> tuple[str, ...]:
    return (brand,) + item.brand_words.get(brand, ())


def _latest(where: str, columns: str) -> str:
    return (f"SELECT {columns} FROM purchases WHERE {where} ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1")


def t11_latest_price(data: UserData, rng: random.Random) -> Spec | None:
    item = _pick_item(data, rng, periods.no_period(), lambda i: not i.weight_g and not i.litres)
    if item is None:
        return None
    target = _latest(item_is(item.name), f"receipt_date, vendor, currency, {UNIT_PRICE} AS price, size_amount, size_unit")
    return _spec("T11", f"What the user paid for {item.name} the last time they bought it.", target,
                 periods.no_period(), item_words(item), item=item.name)  # fmt: skip


def t11k_latest_per_kilo(data: UserData, rng: random.Random) -> Spec | None:
    item = _pick_item(data, rng, periods.no_period(), lambda i: bool(i.weight_g or i.litres) or any(
        s.unit in ("g", "ml") for s in i.sizes))  # fmt: skip
    if item is None:
        return None
    unit, per = _per_kilo_unit(data, item)
    target = _latest(f"{item_is(item.name)} AND size_unit = '{unit}'",
                     f"receipt_date, vendor, currency, ROUND({UNIT_PRICE} / size_amount * 1000, 2) AS price_per_{per}")
    return _spec("T11k", f"What the user paid per {per} for {item.name} the last time.", target, periods.no_period(),
                 item_words(item), _per_words(per), item=item.name)  # fmt: skip


def _per_kilo_unit(data: UserData, item: Item) -> tuple[str, str]:
    units = {line.size_unit for _, line in data.lines if line.item == item.name and line.size_unit in ("g", "ml")}
    unit = "g" if "g" in units or not units else "ml"
    return unit, "kilo" if unit == "g" else "litre"


def _per_words(per: str) -> tuple[str, ...]:
    return ("kilo", "kg", "kilou") if per == "kilo" else ("litre", "liter", "litr")


def _average(item: Item, p: Period, price: str, per: str | None, unit: str = "") -> str:
    """The average, lowest and highest price: per pack size for packaged items, per kilo or litre otherwise."""
    group = "currency" if per else "currency, size_amount, size_unit"
    name = f"_per_{per}" if per else ""
    columns = (f"currency{', size_amount, size_unit' if not per else ''}, COUNT(*) AS purchase_count, "
               f"ROUND(AVG({price}), 2) AS average_price{name}, ROUND(MIN({price}), 2) AS lowest{name or '_price'}, "
               f"ROUND(MAX({price}), 2) AS highest{name or '_price'}")  # fmt: skip
    sized = f"size_unit = '{unit}'" if unit else ""
    return f"SELECT {columns} FROM purchases{_where(item_is(item.name), sized, p.sql)} GROUP BY {group}"


def t12_average_price(data: UserData, rng: random.Random) -> Spec | None:
    p = _period(data, rng) if rng.random() < 0.4 else periods.no_period()
    item = _pick_item(data, rng, p, lambda i: not i.weight_g and not i.litres)
    if item is None:
        return None
    return _spec("T12", f"What the user usually pays for {item.name} (the average, with the lowest and highest), "
                 f"{p.description}.", _average(item, p, UNIT_PRICE, None), p, item_words(item),
                 item=item.name)  # fmt: skip


def t12k_average_per_kilo(data: UserData, rng: random.Random) -> Spec | None:
    p = _period(data, rng) if rng.random() < 0.4 else periods.no_period()
    item = _pick_item(data, rng, p, lambda i: bool(i.weight_g or i.litres) or any(s.unit in ("g", "ml") for s in i.sizes))
    if item is None:
        return None
    unit, per = _per_kilo_unit(data, item)
    price = f"{UNIT_PRICE} / size_amount * 1000"
    target = _average(item, p, price, per, unit)
    return _spec("T12k", f"What the user usually pays per {per} for {item.name} (average, lowest, highest), "
                 f"{p.description}.", target, p, item_words(item), _per_words(per), item=item.name)  # fmt: skip


def t13_compare_shops(data: UserData, rng: random.Random) -> Spec | None:
    p = _period(data, rng) if rng.random() < 0.3 else periods.no_period()
    options = []
    for name in data.items:
        by_unit: dict[str | None, set[str]] = {}
        for r, line in data.lines:
            if line.item == name and _within(r.day, p):
                by_unit.setdefault(line.size_unit, set()).add(r.shop)
        options += [(name, unit, sorted(shops)) for unit, shops in by_unit.items() if len(shops) >= 2]
    if not options:
        return None
    name, unit, shops = rng.choice(options)
    first, second = rng.sample(shops, 2)
    item = data.catalogue.item(name)
    if unit in ("g", "ml"):
        price, column, condition, how = (f"{UNIT_PRICE} / size_amount * 100", "average_price_per_100",
                                         "size_unit IN ('g', 'ml')", "per 100 g or ml")  # fmt: skip
    elif unit == "pcs":
        price, column, condition, how = f"{UNIT_PRICE} / size_amount", "average_price_per_piece", "size_unit = 'pcs'", "per piece"
    else:
        price, column, condition, how = UNIT_PRICE, "average_price", "size_amount IS NULL", "per unit"
    target = (f"SELECT vendor, currency, COUNT(*) AS purchase_count, ROUND(AVG({price}), 2) AS {column} FROM purchases"
              f"{_where(item_is(name), f'vendor IN ({quoted(first)}, {quoted(second)})', condition, p.sql)} "
              "GROUP BY vendor, currency, size_unit")  # fmt: skip
    return _spec("T13", f"Whether {name} was cheaper at {first} or at {second}, by what the user paid ({how}), "
                 f"{p.description}.", target, p, item_words(item), shop_words(data.shop(first)),
                 shop_words(data.shop(second)), item=name, shops=[first, second], compared=how)  # fmt: skip


def t14_times(data: UserData, rng: random.Random) -> Spec | None:
    p = _period(data, rng)
    item = _pick_item(data, rng, p)
    if item is None:
        return None
    target = f"SELECT COUNT(DISTINCT receipt_id) AS times FROM purchases{_where(item_is(item.name), p.sql)}"
    return _spec("T14", f"How many times the user bought {item.name} (on how many receipts), {p.description}.",
                 target, p, item_words(item), item=item.name)  # fmt: skip


def t15_quantity(data: UserData, rng: random.Random) -> Spec | None:
    p = _period(data, rng)
    item = _pick_item(data, rng, p, lambda i: not i.weight_g and not i.litres)
    if item is None:
        return None
    target = f"SELECT SUM(quantity) AS quantity_bought FROM purchases{_where(item_is(item.name), p.sql)}"
    return _spec("T15", f"How many {item.name} the user bought (how many units in total), {p.description}.", target,
                 p, item_words(item), item=item.name)  # fmt: skip


def t16_receipts(data: UserData, rng: random.Random) -> Spec:
    p = _period(data, rng)
    shop = _pick_shop(data, rng, p) if rng.random() < 0.3 else None
    condition = f"vendor = {quoted(shop.name)}" if shop else ""
    target = f"SELECT COUNT(*) AS receipt_count FROM receipts{_where(condition, p.sql)}"
    where = f" from {shop.name}" if shop else ""
    return _spec("T16", f"How many receipts the user has{where}, {p.description}.", target, p,
                 shop_words(shop) if shop else (), shop=shop.name if shop else None)  # fmt: skip


def t17_two_months(data: UserData, rng: random.Random) -> Spec | None:
    category = rng.choice(data.categories) if rng.random() < 0.5 else None
    if category is not None and category not in data.catalogue.default_categories + tuple(data.user.private_categories):
        category = None
    if rng.random() < 0.5:
        first, second = periods.last_month(data.today), periods.this_month(data.today)
        span = ("receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' "
                "AND receipt_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'")
    else:
        months = sorted(rng.sample([m for m in range(1, 13) if m != data.today.month], 2),
                        key=lambda m: periods.named_month(data.today, m).start)  # fmt: skip
        first, second = (periods.named_month(data.today, m) for m in months)
        if first.start < data.first_day:
            return None
        if first.end == second.start:
            span = f"receipt_date >= '{first.start}' AND receipt_date < '{second.end}'"
        else:
            span = f"({first.sql} OR {second.sql})"
    view, amount = ("category_spending", "amount") if category else ("receipts", "total")
    condition = f"category = {quoted(category)}" if category else ""
    target = (f"SELECT date_trunc('month', receipt_date) AS month, currency, SUM({amount}) AS total_spent, "
              f"SUM({amount}_usd) AS total_spent_usd FROM {view}{_where(condition, span)} "
              "GROUP BY month, currency ORDER BY month, currency")  # fmt: skip
    on = f" on {category}" if category else ""
    return Spec("T17", "sql", f"Whether the user spent more{on} {first.description} or {second.description}.",
                target, tuple(g for g in (category_words(data.catalogue, category) if category else (), first.words,
                                          second.words) if g),
                labels={"period": f"{first.kind}+{second.kind}", "category": category})  # fmt: skip


def t18_weight(data: UserData, rng: random.Random) -> Spec | None:
    p = _period(data, rng)
    measured = lambda i: bool(i.weight_g or i.litres) or any(s.unit in ("g", "ml", "pcs") for s in i.sizes)
    item = _pick_item(data, rng, p, measured)
    if item is None:
        return None
    units = {line.size_unit for _, line in data.lines if line.item == item.name and line.size_unit}
    unit = "g" if "g" in units else "ml" if "ml" in units else "pcs"
    if unit == "pcs":
        dozens = item.name == "eggs" or rng.random() < 0.3
        amount = "/ 12 AS dozens" if dozens else "AS pieces"
        how, words = ("dozens", ("dozen", "dazine", "dazzine", "dozens")) if dozens else ("pieces", ())
    else:
        amount = f"/ 1000 AS {'kilos' if unit == 'g' else 'litres'}"
        how, words = ("kilos", ("kilo", "kg", "kilou")) if unit == "g" else ("litres", ("litre", "liter", "litr"))
    target = (f"SELECT SUM(quantity * size_amount) FILTER (WHERE size_unit = '{unit}') {amount}, "
              "COUNT(*) FILTER (WHERE size_amount IS NULL) AS purchases_without_size "
              f"FROM purchases{_where(item_is(item.name), p.sql)}")  # fmt: skip
    return _spec("T18", f"How many {how} of {item.name} the user bought, {p.description}.", target, p,
                 item_words(item), words, item=item.name, measure=how)  # fmt: skip


def t19_month_so_far(data: UserData, rng: random.Random) -> Spec:
    target = ("SELECT date_trunc('month', receipt_date) AS month, currency, SUM(total) AS total_spent, "
              "SUM(total_usd) AS total_spent_usd FROM receipts "
              "WHERE (receipt_date >= date_trunc('month', CURRENT_DATE) AND receipt_date <= CURRENT_DATE) "
              "OR (receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' "
              "AND receipt_date <= CURRENT_DATE - INTERVAL '1 month') GROUP BY month, currency ORDER BY month, currency")
    return Spec("T19", "sql", "The user's spending this month so far compared with the same days of last month (the "
                "month is not over yet).", target, (("hal shaher", "this month"), ("li mara2", "last month", "el ablo",
                                                                                  "li ablo", "previous month")),
                labels={"period": "month_so_far"})  # fmt: skip


def t20_percent_change(data: UserData, rng: random.Random) -> Spec:
    this = "receipt_date >= date_trunc('month', CURRENT_DATE)"
    last = "receipt_date < date_trunc('month', CURRENT_DATE)"
    target = (f"SELECT SUM(total_usd) FILTER (WHERE {this}) AS this_month_usd, "
              f"SUM(total_usd) FILTER (WHERE {last}) AS last_month_usd, "
              f"ROUND((SUM(total_usd) FILTER (WHERE {this}) - SUM(total_usd) FILTER (WHERE {last})) "
              f"/ NULLIF(SUM(total_usd) FILTER (WHERE {last}), 0) * 100, 1) AS percent_change FROM receipts "
              "WHERE receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' "
              "AND receipt_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'")  # fmt: skip
    return Spec("T20", "sql", "By what percent the user's spending this month changed from last month.", target,
                (("%", "percent", "bel miyye", "bil miye", "pourcentage", "nesbe"),), labels={"period": "two_months"})


SQL_TEMPLATES: dict[str, Callable[[UserData, random.Random], Spec | None]] = {
    "T1": t1_total, "T2": t2_total_in_dollars, "T3": t3_category, "T4": t4_where_the_money_went,
    "T5": t5_top_categories, "T6": t6_shop, "T7": t7_top_shop, "T8": t8_visits, "T9": t9_item, "T10": t10_brand,
    "T11": t11_latest_price, "T11k": t11k_latest_per_kilo, "T12": t12_average_price, "T12k": t12k_average_per_kilo,
    "T13": t13_compare_shops, "T14": t14_times, "T15": t15_quantity, "T16": t16_receipts, "T17": t17_two_months,
    "T18": t18_weight, "T19": t19_month_so_far, "T20": t20_percent_change,
}  # fmt: skip
# T3 also covers the kinds of product; T9 and T13 are asked most in practice.
SQL_WEIGHTS = {"T3": 2, "T9": 2, "T13": 1.5}


# --- follow-ups: an earlier question and its SQL, then a short question that changes one thing ---


def _follow(template: str, base: Spec, description: str, target: str, *mentions: tuple[str, ...], **labels) -> Spec:
    return Spec(template, "sql", description, target, tuple(m for m in mentions if m), base=base,
                labels={**base.labels, **labels, "base": base.template})  # fmt: skip


def f1_period(data: UserData, rng: random.Random) -> Spec | None:
    base = rng.choice([t1_total, t3_category, t6_shop, t9_item])(data, rng)
    if base is None or base.labels.get("period") in (None, "none"):
        return None
    old = next(p for p in _all_periods(data) if p.kind == base.labels["period"])
    new = _period(data, rng)
    if new.kind == old.kind or not new.sql or not old.sql:
        return None
    return _follow("F1", base, f"The same question for another period: {new.description}.",
                   base.target.replace(old.sql, new.sql), new.words, period=new.kind)  # fmt: skip


def _all_periods(data: UserData) -> list[Period]:
    t = data.today
    found = [periods.this_month(t), periods.last_month(t), periods.this_week(t), periods.last_week(t),
             periods.today_period(t), periods.yesterday(t), periods.this_year(t), periods.since_start_of_year(t),
             periods.weekend(t), periods.summer(t), periods.no_period()]  # fmt: skip
    found += [periods.last_days(t, n) for n in (3, 7, 10, 14, 30)] + [periods.last_weeks(t, n) for n in (2, 3)]
    found += [periods.last_months(t, n) for n in (2, 3, 6)] + [periods.weekday(t, d) for d in range(7)]
    found += [periods.named_month(t, m) for m in range(1, 13)] + [periods.since_month(t, m) for m in range(1, 13)]
    found += [periods.day_range(t, m, a, a + b) for m in range(1, 13) for a in range(1, 16) for b in range(4, 14)]
    return found


def f2_shop(data: UserData, rng: random.Random) -> Spec | None:
    base = rng.choice([t6_shop, t8_visits])(data, rng)
    if base is None or len(data.shops) < 2:
        return None
    other = data.shop(rng.choice([s for s in data.shops if s != base.labels["shop"]]))
    target = base.target.replace(f"vendor = {quoted(base.labels['shop'])}", f"vendor = {quoted(other.name)}")
    return _follow("F2", base, f"The same question about another shop: {other.name}.", target, shop_words(other),
                   shop=other.name)  # fmt: skip


def f3_item(data: UserData, rng: random.Random) -> Spec | None:
    base = rng.choice([t9_item, t14_times])(data, rng)
    if base is None:
        return None
    others = [n for n in data.items if n != base.labels["item"]]
    other = data.catalogue.item(rng.choice(others))
    target = base.target.replace(item_is(base.labels["item"]), item_is(other.name))
    return _follow("F3", base, f"The same question about another item: {other.name}.", target, item_words(other),
                   item=other.name)  # fmt: skip


def f4_narrow_to_shop(data: UserData, rng: random.Random) -> Spec | None:
    base = t9_item(data, rng)
    if base is None:
        return None
    shops = sorted({r.shop for r, line in data.lines if line.item == base.labels["item"]})
    shop = data.shop(rng.choice(shops))
    target = base.target.replace(" GROUP BY currency", f" AND vendor = {quoted(shop.name)} GROUP BY currency")
    return _follow("F4", base, f"The same question, only at {shop.name}.", target, shop_words(shop), shop=shop.name)


def f5_price_before_last(data: UserData, rng: random.Random) -> Spec | None:
    base = t11_latest_price(data, rng)
    if base is None:
        return None
    return _follow("F5", base, "And the time before that: what they paid the purchase before the last one.",
                   base.target.replace("LIMIT 1", "LIMIT 1 OFFSET 1"))  # fmt: skip


def f6_where_last_bought(data: UserData, rng: random.Random) -> Spec | None:
    base = rng.choice([t11_latest_price, t9_item])(data, rng)
    if base is None:
        return None
    return _follow("F6", base, "Which shop they bought it from the last time.",
                   _latest(item_is(base.labels["item"]), "receipt_date, vendor"))  # fmt: skip


FOLLOW_UPS = {"F1": f1_period, "F2": f2_shop, "F3": f3_item, "F4": f4_narrow_to_shop, "F5": f5_price_before_last,
              "F6": f6_where_last_bought}  # fmt: skip


# --- CLARIFY, UNSUPPORTED and REPLY: code decides what, Qwen writes the words ---


def _closest(data: UserData, item: Item) -> str | None:
    same = [n for n in data.items if data.catalogue.item(n).group == item.group and item.group]
    same = same or [n for n in data.items if data.catalogue.item(n).category == item.category]
    return min(same) if same else None


def c1_unknown_item(data: UserData, rng: random.Random) -> Spec | None:
    missing = [item for item in data.catalogue.items if item.name not in data.items and _closest(data, item)]
    if not missing:
        return None
    item = rng.choice(missing)
    suggestion = _closest(data, item)
    return Spec("C1", "clarify", f"How much the user spent on {item.name}, which they have never bought.", None,
                (item_words(item),), f"Say they have no {item.name} on their receipts and ask whether they mean "
                f"{suggestion}.", labels={"item": item.name, "suggestion": suggestion})  # fmt: skip


def c2_unknown_shop(data: UserData, rng: random.Random) -> Spec | None:
    missing = [shop for shop in data.catalogue.shops if shop.name not in data.shops]
    shop = rng.choice(missing)
    same_kind = sorted(s for s in data.shops if data.shop(s).kind == shop.kind)
    suggestion = same_kind[0] if same_kind else None
    hint = f"Say they have no receipts from {shop.name}" + (f" and ask whether they mean {suggestion}." if suggestion
                                                             else " and ask which shop they mean.")  # fmt: skip
    return Spec("C2", "clarify", f"How much the user spent at {shop.name}, where they have no receipts.", None,
                (shop_words(shop),), hint, labels={"shop": shop.name, "suggestion": suggestion})


def c3_nothing_to_refer_to(data: UserData, rng: random.Random) -> Spec:
    what = rng.choice(["what the last one cost", "how much they paid there", "how many times they bought it",
                       "whether that one was cheaper", "the total for the same thing"])  # fmt: skip
    return Spec("C3", "clarify", f"A question that refers to something earlier ({what}), with nothing earlier in the "
                "chat, so it is not clear what 'it', 'there' or 'the last one' is.", None, (),
                "Ask which item, shop or period they mean.", labels={})  # fmt: skip


def c4_unclear_period(data: UserData, rng: random.Random) -> Spec:
    period, words = rng.choice([("'kanoun' alone (it could be December or January)", ("kanoun",)),
                                ("this semester", ("semester", "fasl")),
                                ("the start of the year (bi awal el sene), without 'since'", ("awal el sene",))])
    return Spec("C4", "clarify", f"How much the user spent in {period}.", None, (words,),
                "Ask exactly which dates or month they mean.", labels={"period": words[0]})  # fmt: skip


def c5_no_such_items(data: UserData, rng: random.Random) -> Spec:
    what, words = rng.choice([("gifts", ("hadeye", "hadaya", "hdaya", "gifts", "gift")),
                              ("repairs", ("tasli7", "tesli7", "repairs", "siyene", "siyane", "maintenance"))])
    return Spec("C5", "clarify", f"How much the user spent on {what}, which is not a category and is not on any of "
                "their receipts.", None, (words,), f"Say nothing on their receipts is marked as {what} and ask which "
                "items or shop they mean.", labels={"group": what})  # fmt: skip


def c6_say_again(data: UserData, rng: random.Random) -> Spec:
    what = rng.choice(["they did not understand the last answer and want it explained more simply",
                       "the last answer was not what they meant"])
    return Spec("C6", "clarify", f"The user says {what}.", None, (), "Ask what exactly they want to know.",
                labels={})  # fmt: skip


UNSUPPORTED = (
    ("U1", "setting or checking a budget (e.g. putting a budget on shopping, or whether they are over budget)"),
    ("U2", "a prediction about future spending (e.g. how much they will spend next month)"),
    ("U3", "prices in shops in general, offers or stock, not what they paid (e.g. what an iPhone costs now)"),
    ("U4", "advice on what to buy or how to save"),
    ("U5", "something receipts cannot show: their salary, their bank balance, or what another person spent"),
)
REPLIES = (
    ("R1", "a greeting (hi, marhaba, sabah el kheir)", "Greet them back and say what you can help with."),
    ("R2", "thanks or 'ok, that is what I wanted'", "Say you're welcome."),
    ("R3", "what the assistant can do", ("Say it answers questions about their own receipts: totals, categories, "
                                          "shops, items, prices and comparisons.")),
    ("R4", "small talk (a joke, how are you, a reaction like 'wow')", "Reply briefly and kindly, with no amounts."),
)


def unsupported(data: UserData, rng: random.Random) -> Spec:
    template, about = rng.choice(UNSUPPORTED)
    return Spec(template, "unsupported", f"A question about {about}.", "UNSUPPORTED", labels={})


def reply(data: UserData, rng: random.Random) -> Spec:
    template, about, hint = rng.choice(REPLIES)
    return Spec(template, "reply", f"The user sends {about}.", None, (), hint + " Never state amounts.", labels={})


CLARIFY = {"C1": c1_unknown_item, "C2": c2_unknown_shop, "C3": c3_nothing_to_refer_to, "C4": c4_unclear_period,
           "C5": c5_no_such_items, "C6": c6_say_again}  # fmt: skip
# The approved mix of things to ask (round 1): ~75% SQL of which ~15 points follow-ups, ~10% CLARIFY, ~8%
# UNSUPPORTED, ~7% REPLY.
MIX = {"sql": 60, "follow_up": 15, "clarify": 10, "unsupported": 8, "reply": 7}


def make_specs(data: UserData, count: int, seed: str) -> list[Spec]:
    """`count` things to ask for this user, in the approved mix, from a fixed seed."""
    rng = random.Random(seed)
    kinds, weights = zip(*MIX.items(), strict=True)
    sql_names = list(SQL_TEMPLATES)
    sql_weights = [SQL_WEIGHTS.get(name, 1) for name in sql_names]
    specs: list[Spec] = []
    attempts = 0
    while len(specs) < count and attempts < count * 50:
        attempts += 1
        kind = rng.choices(kinds, weights)[0]
        if kind == "sql":
            maker = SQL_TEMPLATES[rng.choices(sql_names, sql_weights)[0]]
        elif kind == "follow_up":
            maker = FOLLOW_UPS[rng.choice(list(FOLLOW_UPS))]
        elif kind == "clarify":
            maker = CLARIFY[rng.choice(list(CLARIFY))]
        else:
            maker = unsupported if kind == "unsupported" else reply
        spec = maker(data, rng)
        if spec is not None:
            specs.append(spec)
    return specs

