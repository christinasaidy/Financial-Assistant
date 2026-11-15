"""Batch 3 (approved by the user on 2026-11-15, after the research critique): the gaps batch 2 left, built on new
synthetic users so batch 1 and 2 stay exactly as they were.

- Users 32-39 train, 40-41 validation (31 is the test user), from the catalogue plus its batch-3 extension (the
  items, shops and spellings of the user's 60 seed questions). Their "today" is set, spread over the year: numbered
  users after 30 would otherwise all land in 2028 and every named month would point to last year.
- New question types, one per approved worked example (B1-B10), with the SQL shapes the prompt now teaches.
- Existing question types with the periods and wordings the training data lacked: totals, shop totals, top shop and
  receipt counts for this month, last month and yesterday; since a weekday; "sarle" (up to now); comparisons that
  do not say "100"; negations ("bala ma t2elle kam marra, adde dafa3et"); percent change; where the money went.
- Many more CLARIFY and UNSUPPORTED questions (their share of Arabizi had fallen to 6.5%).

Code writes every SQL target; the questions are written for each spec afterwards, imitating the user's seeds.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from research.dataset import periods
from research.dataset import templates as t
from research.dataset.catalogue import BATCH3_EXTENSION, Catalogue, load_catalogue
from research.dataset.periods import Period
from research.dataset.templates import Spec, UserData, _within
from research.dataset.users import make_user

SEED_PREFIX = "fyp-dataset/batch3"
TODAYS = {32: date(2026, 3, 17), 33: date(2026, 5, 26), 34: date(2026, 7, 8), 35: date(2026, 8, 19),
          36: date(2026, 10, 1), 37: date(2026, 11, 25), 38: date(2027, 1, 13), 39: date(2027, 4, 21),
          40: date(2026, 6, 10), 41: date(2027, 2, 24)}  # fmt: skip
TRAIN, VALIDATION = tuple(range(32, 40)), (40, 41)

RESTAURANT_WORDS = ("mat3am", "mata3em", "matta3em", "mat3am", "restaurant", "restaurants", "mat3ame")
SUPERMARKET_WORDS = ("supermarket", "supermarkets", "sobermarket", "soupermarket", "super market")
MOST_WORDS = ("aktar", "most", "aktar shi")
USUAL_WORDS = ("3adatan", "aadatan", "bel 3ade", "bl 3ade", "bel aade", "bl aade", "aade", "usually", "normally", "3ade")
MONTHLY_WORDS = ("bl shaher", "bel shaher", "kel shaher", "a month", "per month", "monthly", "bil shaher")
NEGATION_WORDS = ("bala ma", "ma t2elle", "ma t2ele", "ma t2olle", "ma t2oul", "msh", "mesh", "mish", "not")
SARLE_WORDS = ("sarle", "sarli", "sar le", "sar li", "so far", "up to now", "until now", "till now")  # English too
FIRST_WORDS = ("adde sarle", "adesh sarle", "since when", "emta", "men emta", "addesh sarle", "aday sarle")
CHANGE_WORDS = ("zed", "zad", "ghele", "ghili", "na2as", "ne2sit", "no2is", "pricier", "aghla", "arkhas", "went up", "go up", "went down",
                "go down", "changed", "cheaper", "more expensive", "zeyde", "nazal", "tele3")
CHEAPEST_WORDS = ("arkhas", "aghla", "cheapest", "cheaper", "most expensive", "a2al", "arkhas shi", "aghla shi")
SAME_BRAND_WORDS = ("nafs brand", "nafes brand", "nafs el brand", "same brand", "nafs el marka", "la nafs brand")


def load_batch3_catalogue() -> Catalogue:
    return load_catalogue(extension=BATCH3_EXTENSION)


def batch3_user(number: int, catalogue: Catalogue | None = None) -> UserData:
    catalogue = catalogue or load_batch3_catalogue()
    return UserData(make_user(catalogue, number, today=TODAYS[number]), catalogue)


# --- periods the batch-3 questions use ---


def last_two_days(today: date) -> Period:
    p = periods.last_days(today, 2)
    return Period(p.kind, p.sql, p.start, p.end, p.description,
                  p.words + ("yawmein", "yomein", "ywmein", "2 days", "two days"))


def last_five_months(today: date) -> Period:
    start = periods._months_before(today, 5) + timedelta(days=1)
    return Period("last_5_months", "receipt_date > CURRENT_DATE - INTERVAL '5 months' AND receipt_date <= CURRENT_DATE",
                  start, today + timedelta(days=1), "the last 5 months (up to today)",
                  ("5", "five", "khamse", "5 2oshor", "5 ashhor", "5 shhour"))  # fmt: skip


COMMON = {"this_month": periods.this_month, "last_month": periods.last_month, "yesterday": periods.yesterday,
          "this_week": periods.this_week, "last_week": periods.last_week, "today": periods.today_period,
          "day_before_yesterday": periods.day_before_yesterday, "since_yesterday": periods.since_yesterday,
          "last_2_days": last_two_days, "since_start_of_year": periods.since_start_of_year,
          "last_5_months": last_five_months}  # fmt: skip


# The user's own ways of saying common periods (her 60 seeds, 2026-11-15), accepted for batch 3 only: adding them to
# periods.py would change the saved batch 1-2 prompts.
EXTRA_WORDS = {
    "this_month": ("he el shaher", "heda el shaher", "heda l shaher", "hayda el shaher", "he l shaher"),
    "last_month": ("el shaher el mara2", "el shaher el madi", "el shaher li ata3", "ekher shaher"),
    "this_week": ("he el jemaa", "he el jem3a", "heda el osbou3"),
    "last_week": ("haydik el jemaa", "haydik el jem3a", "jem3a el madye", "el jem3a el madye", "el jemaa el madye"),
}


def period_named(data: UserData, kind: str, rng: random.Random) -> Period:
    if kind == "since_weekday":
        return periods.since_weekday(data.today, rng.randrange(7))
    if kind == "since_month":
        return periods.since_month(data.today, periods._a_past_month(rng, data.today))
    if kind == "none":
        return periods.no_period()
    p = COMMON[kind](data.today)
    extra = tuple(w for w in EXTRA_WORDS.get(kind, ()) if w not in p.words)
    return Period(p.kind, p.sql, p.start, p.end, p.description, p.words + extra) if extra else p


# --- helpers ---


def _units(data: UserData, item: str, period: Period | None = None) -> dict[str | None, set[str]]:
    """The shops an item was bought at, per size unit (None = no size)."""
    found: dict[str | None, set[str]] = {}
    for r, line in data.lines:
        if line.item == item and (period is None or _within(r.day, period)):
            found.setdefault(line.size_unit, set()).add(r.shop)
    return found


def _basis(unit: str | None) -> tuple[str, str, str, str]:
    """(price, column, condition, wording) for comparing prices of lines with this size unit."""
    if unit in ("g", "ml"):
        return (f"{t.UNIT_PRICE} / size_amount * 100", "average_price_per_100", "size_unit IN ('g', 'ml')",
                "per 100 g or ml")  # fmt: skip
    if unit == "pcs":
        return f"{t.UNIT_PRICE} / size_amount", "average_price_per_piece", "size_unit = 'pcs'", "per piece"
    return t.UNIT_PRICE, "average_price", "size_amount IS NULL", "by unit price (no size)"


def _comparison(item: str, shops: tuple[str, ...], unit: str | None, *extra: str, order: bool = False) -> str:
    price, column, condition, _ = _basis(unit)
    where = [t.item_is(item)] + ([f"vendor IN ({', '.join(t.quoted(s) for s in shops)})"] if shops else []) + [
        condition, *extra]  # fmt: skip
    group = "vendor, currency, size_unit" if shops else "vendor, currency"
    tail = f" ORDER BY {column}, vendor" if order else ""
    return (f"SELECT vendor, currency, COUNT(*) AS purchase_count, ROUND(AVG({price}), 2) AS {column} FROM purchases"
            f"{t._where(*where)} GROUP BY {group}{tail}")  # fmt: skip


def _bought_items(data: UserData, period: Period | None = None, least: int = 1) -> list[str]:
    counts: dict[str, int] = {}
    for r, line in data.lines:
        if period is None or _within(r.day, period):
            counts[line.item] = counts.get(line.item, 0) + 1
    return sorted(name for name, n in counts.items() if n >= least)


# --- the new question types (worked examples approved 2026-11-15) ---


def b1_list(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    p = period_named(data, kind, rng)
    if not data.receipts_in(p):
        return None
    target = (f"SELECT receipt_date, vendor, item_name, currency, line_total FROM purchases{t._where(p.sql)} "
              "ORDER BY receipt_date")
    return t._spec("B1", f"A list of everything the user bought or spent on, item by item, {p.description}.",
                   target, p)


def b2_most_visited(data: UserData, rng: random.Random, kind: str, shops: str) -> Spec | None:
    p = period_named(data, kind, rng)
    if shops == "any":
        target = (f"SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM receipts{t._where(p.sql)} "
                  "GROUP BY vendor ORDER BY visits DESC LIMIT 1")
        return t._spec("B2", f"Which shop the user went to the most times (visits, not money), {p.description}.",
                       target, p, MOST_WORDS, shops=shops)
    category, words, name = (("Dining", RESTAURANT_WORDS, "restaurant") if shops == "restaurants"
                             else ("Groceries", SUPERMARKET_WORDS, "supermarket"))  # fmt: skip
    if not any(r.category == category for r in data.receipts_in(p)):
        return None
    target = (f"SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM category_spending"
              f"{t._where(f'category = {t.quoted(category)}', p.sql)} GROUP BY vendor ORDER BY visits DESC LIMIT 1")
    return t._spec("B2", f"Which {name} the user went to the most times (visits, not money), {p.description}.",
                   target, p, words, MOST_WORDS, shops=shops)


def b3_cheapest_anywhere(data: UserData, rng: random.Random, dearest: bool = False) -> Spec | None:
    options = [(item, unit) for item in data.items for unit, shops in _units(data, item).items() if len(shops) >= 2]
    if not options:
        return None
    item, unit = rng.choice(sorted(options, key=str))
    words = t.item_words(data.catalogue.item(item))
    which = "most expensive" if dearest else "cheapest"
    return Spec("B3", "sql", f"At which shop {item} was {which}, comparing every shop the user bought it at "
                f"({_basis(unit)[3]}); no shop is named.", _comparison(item, (), unit, order=True),
                (words, CHEAPEST_WORDS), labels={"period": "none", "item": item, "compared": _basis(unit)[3]})


def _price_basis(data: UserData, item: str) -> tuple[str, str, str]:
    """(price, condition, suffix): per kilo or litre for sizes in g or ml, otherwise the unit price."""
    units = _units(data, item)
    for unit, per in (("g", "kilo"), ("ml", "litre")):
        if unit in units:
            return f"{t.UNIT_PRICE} / size_amount * 1000", f"size_unit = '{unit}'", f"_per_{per}"
    return t.UNIT_PRICE, "", ""


# Bills and recharges have no price that changes or a usual monthly amount worth asking about.
NOT_PRICED = frozenset({"electricity bill", "generator subscription", "internet", "streaming subscription",
                                           "music subscription", "gym membership", "phone recharge"})


def b4_price_change(data: UserData, rng: random.Random) -> Spec | None:
    candidates = []
    for item in (i for i in data.items if i not in NOT_PRICED):
        price, condition, _ = _price_basis(data, item)
        unit = condition.split("'")[1] if condition else None
        if sum(1 for _, line in data.lines if line.item == item and (unit is None or line.size_unit == unit)) >= 2:
            candidates.append(item)
    if not candidates:
        return None
    item = rng.choice(candidates)
    price, condition, suffix = _price_basis(data, item)

    def one(offset: str) -> str:
        return (f"(SELECT receipt_date, {price} AS price FROM purchases{t._where(t.item_is(item), condition)} "
                f"ORDER BY receipt_date DESC, receipt_id DESC LIMIT 1{offset})")

    target = ("SELECT latest.receipt_date AS latest_date, ROUND(latest.price, 2) AS latest_price, "
              "previous.receipt_date AS previous_date, ROUND(previous.price, 2) AS previous_price, "
              "ROUND((latest.price - previous.price) / NULLIF(previous.price, 0) * 100, 1) AS percent_change "
              f"FROM {one('')} AS latest, {one(' OFFSET 1')} AS previous")  # fmt: skip
    per = suffix.replace("_", " ").strip()
    return Spec("B4", "sql", f"Whether the price of {item} went up or down{(' ' + per) if per else ''}, and by how "
                "much or what percent: the latest purchase against the one before it.", target,
                (t.item_words(data.catalogue.item(item)), CHANGE_WORDS), labels={"period": "none", "item": item})


def b5_average_this_month_vs_last(data: UserData, rng: random.Random) -> Spec | None:
    two = Period("this_and_last_month", "", periods.last_month(data.today).start, periods.this_month(data.today).end,
                 "", ())  # fmt: skip
    candidates = [i for i in _bought_items(data, two, least=2) if i not in NOT_PRICED]
    if not candidates:
        return None
    item = rng.choice(candidates)
    price, condition, suffix = _price_basis(data, item)
    target = (f"SELECT date_trunc('month', receipt_date) AS month, ROUND(AVG({price}), 2) AS average_price{suffix} "
              f"FROM purchases{t._where(t.item_is(item), condition, periods.LAST_MONTH.split(' AND ')[0])} "
              "GROUP BY month ORDER BY month")  # fmt: skip
    return Spec("B5", "sql", f"Whether the user's average price for {item} went down (or up) this month compared "
                "with last month.", target, (t.item_words(data.catalogue.item(item)), CHANGE_WORDS),
                labels={"period": "this_vs_last_month", "item": item})


def b6_since_when(data: UserData, rng: random.Random) -> Spec | None:
    items = [i for i in data.items if i not in NOT_PRICED]
    item = rng.choice(items) if items else None
    if item is None:
        return None
    shops = sorted({r.shop for r, line in data.lines if line.item == item})
    shop = rng.choice(shops) if shops and rng.random() < 0.5 else None
    where = [t.item_is(item)] + ([f"vendor = {t.quoted(shop)}"] if shop else [])
    target = f"SELECT MIN(receipt_date) AS first_bought, COUNT(DISTINCT receipt_id) AS times FROM purchases{t._where(*where)}"
    mentions = [t.item_words(data.catalogue.item(item)), FIRST_WORDS] + ([t.shop_words(data.shop(shop))] if shop else [])
    at = f" at {shop}" if shop else ""
    return Spec("B6", "sql", f"Since when the user has been buying {item}{at} (the first purchase), and how many "
                "times since.", target, tuple(mentions), labels={"period": "none", "item": item, "shop": shop})


def b7_usual_per_month(data: UserData, rng: random.Random, money: bool) -> Spec | None:
    months = Period("last_3_complete_months", "receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '3 months' "
                    "AND receipt_date < date_trunc('month', CURRENT_DATE)",
                    periods._months_before(periods.this_month(data.today).start, 3), periods.this_month(data.today).start,
                    "", ())  # fmt: skip
    pool = [n for n in _bought_items(data, months) if n not in NOT_PRICED and (money or not (data.catalogue.item(n).weight_g
                                                                    or data.catalogue.item(n).litres))]
    if not pool:
        return None
    item = rng.choice(pool)
    if money:
        target = ("SELECT currency, ROUND(SUM(line_total) / 3.0, 2) AS usual_per_month, "
                  f"ROUND(SUM(line_total_usd) / 3.0, 2) AS usual_per_month_usd FROM purchases"
                  f"{t._where(t.item_is(item), months.sql)} GROUP BY currency")
        what = f"How much the user usually spends on {item} a month"
    else:
        target = f"SELECT ROUND(SUM(quantity) / 3.0, 1) AS usual_per_month FROM purchases{t._where(t.item_is(item), months.sql)}"
        what = f"How many {item} the user usually buys a month"
    return Spec("B7", "sql", f"{what} (the last 3 complete months, divided by 3).", target,
                (t.item_words(data.catalogue.item(item)), USUAL_WORDS, MONTHLY_WORDS),
                labels={"period": "last_3_complete_months", "item": item, "money": money})


def b8_brand_between_shops(data: UserData, rng: random.Random) -> Spec | None:
    options = []
    for item in data.items:
        by: dict[tuple[str, str | None], set[str]] = {}
        for r, line in data.lines:
            if line.item == item and line.brand:
                by.setdefault((line.brand, line.size_unit), set()).add(r.shop)
        options += [(item, brand, unit, sorted(shops)) for (brand, unit), shops in by.items() if len(shops) >= 2]
    if not options:
        return None
    item, brand, unit, shops = rng.choice(sorted(options, key=str))
    first, second = rng.sample(shops, 2)
    catalogue_item = data.catalogue.item(item)
    target = _comparison(item, (first, second), unit, f"brand = {t.quoted(brand)}")
    return Spec("B8", "sql", f"Whether {brand} {item} was cheaper at {first} or at {second} ({_basis(unit)[3]}).",
                target, (t.item_words(catalogue_item), t._brand_words(catalogue_item, brand),
                         t.shop_words(data.shop(first)), t.shop_words(data.shop(second))),
                labels={"period": "none", "item": item, "brand": brand, "shops": [first, second]})


def b9_restaurant_receipts(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    p = period_named(data, kind, rng)
    dining = "category = 'Dining'"
    target = f"SELECT COUNT(DISTINCT receipt_id) AS receipt_count FROM category_spending{t._where(dining, p.sql)}"
    return t._spec("B9", f"How many restaurant receipts the user has, {p.description}.", target, p, RESTAURANT_WORDS)


def b10_same_brand(data: UserData, rng: random.Random) -> Spec | None:
    options = []
    for item in data.items:
        for unit, shops in _units(data, item).items():
            for first, second in ((a, b) for a in sorted(shops) for b in sorted(shops) if a < b):
                at = {s: {line.brand for r, line in data.lines if line.item == item and r.shop == s
                          and line.size_unit == unit and line.brand} for s in (first, second)}  # fmt: skip
                if at[first] & at[second]:
                    options.append((item, unit, first, second))
    if not options:
        return None
    item, unit, first, second = rng.choice(options)
    price, _, condition, how = _basis(unit)
    shops = f"vendor IN ({t.quoted(first)}, {t.quoted(second)})"
    target = (f"SELECT brand, vendor, currency, COUNT(*) AS purchase_count, ROUND(AVG({price}), 2) AS average_price "
              f"FROM purchases WHERE {t.item_is(item)} AND {shops} AND {condition} AND brand IN (SELECT brand FROM "
              f"purchases WHERE {t.item_is(item)} AND {shops} AND {condition} GROUP BY brand "
              "HAVING COUNT(DISTINCT vendor) = 2) GROUP BY brand, vendor, currency")  # fmt: skip
    return Spec("B10", "sql", f"For the same brand of {item}, whether it was cheaper at {first} or at {second} "
                f"({how}).", target, (t.item_words(data.catalogue.item(item)), SAME_BRAND_WORDS,
                                      t.shop_words(data.shop(first)), t.shop_words(data.shop(second))),
                labels={"period": "none", "item": item, "shops": [first, second]})


# --- existing question types, with the periods and wordings the data lacked ---


def total(data: UserData, rng: random.Random, kind: str) -> Spec:
    p = period_named(data, kind, rng)
    return t._spec("T1", f"How much the user spent in total, {p.description}.", t.money("receipts", "total", p.sql), p)


def _shop_in(data: UserData, rng: random.Random, p: Period) -> str | None:
    shops = sorted({r.shop for r in data.receipts_in(p)})
    return rng.choice(shops) if shops else None


def shop_total(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    p = period_named(data, kind, rng)
    shop = _shop_in(data, rng, p)
    if shop is None:
        return None
    return t._spec("T6", f"How much the user spent at {shop}, {p.description}.",
                   t.money("receipts", "total", f"vendor = {t.quoted(shop)}", p.sql), p,
                   t.shop_words(data.shop(shop)), shop=shop)  # fmt: skip


def top_shop(data: UserData, rng: random.Random, kind: str) -> Spec:
    p = period_named(data, kind, rng)
    target = (f"SELECT vendor, SUM(total_usd) AS total_spent_usd FROM receipts{t._where(p.sql)} GROUP BY vendor "
              "ORDER BY total_spent_usd DESC LIMIT 1")
    return t._spec("T7", f"Which shop the user spent the most money at, {p.description}.", target, p, MOST_WORDS)


def receipts(data: UserData, rng: random.Random, kind: str, at_shop: bool = False) -> Spec | None:
    p = period_named(data, kind, rng)
    shop = _shop_in(data, rng, p) if at_shop else None
    if at_shop and shop is None:
        return None
    condition = f"vendor = {t.quoted(shop)}" if shop else ""
    where = f" from {shop}" if shop else ""
    return t._spec("T16", f"How many receipts the user has{where}, {p.description}.",
                   f"SELECT COUNT(*) AS receipt_count FROM receipts{t._where(condition, p.sql)}", p,
                   t.shop_words(data.shop(shop)) if shop else (), shop=shop)  # fmt: skip


# Paid once a month, so never asked about as visits, times or units (the user's review, 2026-11-15: "no one in Lebanon
# pays more than once a month la ishtirak el hay").
MONTHLY_KINDS = frozenset({"utility", "subscription", "gym"})
MONTHLY_BILLS = frozenset({"electricity bill", "generator subscription", "internet", "streaming subscription",
                           "music subscription", "gym membership"})


def visits(data: UserData, rng: random.Random, kind: str, negation: bool = False) -> Spec | None:
    p = period_named(data, kind, rng)
    visited = [s for s in sorted({r.shop for r in data.receipts_in(p)}) if data.shop(s).kind not in MONTHLY_KINDS]
    others = [s for s in data.shops if data.shop(s).kind not in MONTHLY_KINDS]
    shop = rng.choice(visited or others) if visited or others else None
    if shop is None:
        return None
    target = f"SELECT COUNT(DISTINCT receipt_id) AS visits FROM receipts{t._where(f'vendor = {t.quoted(shop)}', p.sql)}"
    said = (" They say explicitly they do NOT want how much they spent there, only how many times."
            if negation else "")
    return t._spec("T8", f"How many times the user went to {shop}, {p.description}.{said}", target, p,
                   t.shop_words(data.shop(shop)), NEGATION_WORDS if negation else (), shop=shop,
                   negation=negation)  # fmt: skip


def _item_in(data: UserData, rng: random.Random, p: Period, allowed: Callable = lambda item: True) -> str | None:
    pool = [n for n in _bought_items(data, p) if allowed(data.catalogue.item(n))] or [
        n for n in data.items if allowed(data.catalogue.item(n))]  # fmt: skip
    return rng.choice(pool) if pool else None


def item_spend(data: UserData, rng: random.Random, kind: str, negation: bool = False, sarle: bool = False
               ) -> Spec | None:  # fmt: skip
    p = period_named(data, kind, rng)
    item = _item_in(data, rng, p)
    if item is None:
        return None
    said = (" They say explicitly they do NOT want how many times they bought it, only how much they paid."
            if negation else "")
    so_far = " so far (up to now, 'sarle')" if sarle else ""
    return t._spec("T9", f"How much the user spent on {item}{so_far} (no brand named), {p.description}.{said}",
                   t.money("purchases", "line_total", t.item_is(item), p.sql), p,
                   t.item_words(data.catalogue.item(item)), NEGATION_WORDS if negation else (),
                   SARLE_WORDS if sarle else (), item=item, negation=negation, sarle=sarle)  # fmt: skip


def times_bought(data: UserData, rng: random.Random, kind: str, negation: bool = False) -> Spec | None:
    p = period_named(data, kind, rng)
    item = _item_in(data, rng, p, lambda i: i.name not in MONTHLY_BILLS)
    if item is None:
        return None
    target = f"SELECT COUNT(DISTINCT receipt_id) AS times FROM purchases{t._where(t.item_is(item), p.sql)}"
    said = (" They say explicitly they do NOT want how much they paid, only how many times." if negation else "")
    return t._spec("T14", f"How many times the user bought {item} (on how many receipts), {p.description}.{said}",
                   target, p, t.item_words(data.catalogue.item(item)), NEGATION_WORDS if negation else (),
                   item=item, negation=negation)  # fmt: skip


def quantity(data: UserData, rng: random.Random, kind: str, negation: bool = False) -> Spec | None:
    p = period_named(data, kind, rng)
    item = _item_in(data, rng, p, lambda i: not i.weight_g and not i.litres and i.name not in MONTHLY_BILLS)
    if item is None:
        return None
    target = f"SELECT SUM(quantity) AS quantity_bought FROM purchases{t._where(t.item_is(item), p.sql)}"
    said = (" They say explicitly they do NOT want how much they paid, only how many." if negation else "")
    return t._spec("T15", f"How many {item} the user bought (how many units in total), {p.description}.{said}",
                   target, p, t.item_words(data.catalogue.item(item)), NEGATION_WORDS if negation else (),
                   item=item, negation=negation)  # fmt: skip


def where_money_went(data: UserData, rng: random.Random, kind: str) -> Spec:
    p = period_named(data, kind, rng)
    target = (f"SELECT category, currency, SUM(amount) AS total_spent, SUM(amount_usd) AS total_spent_usd "
              f"FROM category_spending{t._where(p.sql)} GROUP BY category, currency ORDER BY total_spent_usd DESC")
    return t._spec("T4", f"Where the user's money went, split by category, {p.description}.", target, p)


def top_categories(data: UserData, rng: random.Random, kind: str) -> Spec:
    p = period_named(data, kind, rng)
    target = (f"SELECT category, SUM(amount_usd) AS total_spent_usd FROM category_spending"
              f"{t._where(f'category <> {t.quoted(t.TAX_CATEGORY)}', p.sql)} GROUP BY category "
              "ORDER BY total_spent_usd DESC LIMIT 3")  # fmt: skip
    return t._spec("T5", f"The user's biggest expenses: the 3 categories they spent the most on, {p.description}.",
                   target, p, top=3)


def implicit_comparison(data: UserData, rng: random.Random) -> Spec | None:
    """A per-100 comparison between two shops whose question does not say "100" (the user only asks which was
    cheaper); the per-size rule decides the basis, as the prompt says."""
    options = [(item, sorted(shops)) for item in data.items for unit, shops in _units(data, item).items()
               if unit in ("g", "ml") and len(shops) >= 2]
    if not options:
        return None
    item, shops = rng.choice(sorted(options, key=str))
    first, second = rng.sample(shops, 2)
    unit = next(u for u, s in _units(data, item).items() if u in ("g", "ml") and {first, second} <= s)
    return Spec("T13", "sql", f"Whether {item} was cheaper at {first} or at {second}. The user just asks which was "
                "cheaper or where they paid less; they do NOT mention 100 g, grams or a size.",
                _comparison(item, (first, second), unit),
                (t.item_words(data.catalogue.item(item)), t.shop_words(data.shop(first)),
                 t.shop_words(data.shop(second))),
                labels={"period": "none", "item": item, "shops": [first, second], "compared": "per 100 g or ml",
                        "implicit": True})  # fmt: skip


def percent_change(data: UserData, rng: random.Random) -> Spec:
    spec = t.t20_percent_change(data, rng)
    words = spec.mentions[0] + ("nesbit", "nesbet")  # the user's "aday zed nesbit masroufe ..." (2026-11-15)
    return Spec(spec.template, spec.kind, spec.description + " They say it with 'bel miyye' or 'adde zed / na2as'.",
                spec.target, (words,), labels=spec.labels)


def no_such_items(data: UserData, rng: random.Random) -> Spec:
    """C5 with the user's plurals (tasli7at / tosli7at, 2026-11-15) accepted; the shared template stays as it was."""
    spec = t.c5_no_such_items(data, rng)
    extra = ("tasli7at", "tosli7at", "tasli7 el sayara") if spec.labels.get("group") == "repairs" else ()
    return Spec(spec.template, spec.kind, spec.description, spec.target, (spec.mentions[0] + extra,),
                spec.reply_hint, labels=spec.labels)


def lately(data: UserData, rng: random.Random) -> Spec:
    what = rng.choice(["how much they spent", "which shop they went to most", "how much they paid for an item"])
    return Spec("C4", "clarify", f"The user asks {what} 'lately' (hal fatra), with no period.", None,
                (("hal fatra", "lately", "recently", "hal iyem", "hal ayyem"),),
                "Ask exactly which period they mean.", labels={"period": "hal fatra"})  # fmt: skip


def vague_reference(data: UserData, rng: random.Random) -> Spec:
    what = rng.choice(["'that restaurant' (hedek el mat3am) with nothing earlier in the chat",
                       "'that thing' (haydik el shaghle / heda el shi) with nothing earlier",
                       "'the blue one' (heda el shi el azra2) with nothing earlier",
                       "the price of 'it' (ha2o / ha2a) alone, with no item named before",
                       "'the place we talked about last time', which is not in the chat"])  # fmt: skip
    return Spec("C3", "clarify", f"A question about {what}, so it is not clear what they mean.", None, (),
                "Ask which item, shop or period they mean.", labels={})


@dataclass(frozen=True)
class Want:
    """How many specs of one kind to plan, spread over the users."""

    maker: Callable[..., Spec | None]
    count: int
    args: tuple = ()


SQL_WANTS = (
    Want(b1_list, 2, ("day_before_yesterday",)), Want(b1_list, 2, ("yesterday",)), Want(b1_list, 1, ("today",)),
    Want(b1_list, 1, ("last_2_days",)),
    Want(b2_most_visited, 3, ("this_month", "any")), Want(b2_most_visited, 3, ("last_month", "restaurants")),
    Want(b2_most_visited, 3, ("last_week", "supermarkets")),
    Want(b3_cheapest_anywhere, 4), Want(b3_cheapest_anywhere, 2, (True,)),
    Want(b4_price_change, 6), Want(b5_average_this_month_vs_last, 3), Want(b6_since_when, 4),
    Want(b7_usual_per_month, 2, (False,)), Want(b7_usual_per_month, 2, (True,)),
    Want(b8_brand_between_shops, 4), Want(b9_restaurant_receipts, 2, ("none",)),
    Want(b9_restaurant_receipts, 2, ("this_month",)), Want(b10_same_brand, 3),
    Want(total, 2, ("this_month",)), Want(total, 2, ("last_month",)), Want(total, 2, ("yesterday",)),
    Want(total, 1, ("this_week",)), Want(total, 1, ("last_2_days",)), Want(total, 1, ("day_before_yesterday",)),
    Want(total, 1, ("since_weekday",)),
    Want(shop_total, 2, ("since_weekday",)), Want(shop_total, 1, ("this_week",)),
    Want(top_shop, 1, ("last_month",)), Want(top_shop, 2, ("yesterday",)),
    Want(receipts, 2, ("yesterday",)), Want(receipts, 1, ("this_month",)), Want(receipts, 1, ("last_month", True)),
    Want(visits, 3, ("since_weekday",)), Want(visits, 2, ("this_month", True)),
    Want(item_spend, 2, ("since_weekday",)), Want(item_spend, 5, ("none", False, True)),
    Want(item_spend, 1, ("since_month",)), Want(item_spend, 2, ("none", True)),
    Want(times_bought, 2, ("since_start_of_year",)), Want(times_bought, 2, ("this_month", True)),
    Want(quantity, 2, ("this_week", True)),
    Want(implicit_comparison, 13), Want(where_money_went, 2, ("this_week",)),
    Want(top_categories, 2, ("last_5_months",)), Want(percent_change, 2),
)
OTHER_WANTS = (
    Want(vague_reference, 26), Want(lately, 8), Want(t.c1_unknown_item, 10), Want(t.c2_unknown_shop, 8),
    Want(no_such_items, 5), Want(t.c6_say_again, 5), Want(t.unsupported, 30),
)


def plan(numbers: tuple[int, ...], one_each: bool = False, catalogue: Catalogue | None = None
         ) -> dict[int, list[Spec]]:  # fmt: skip
    """Every wanted spec, given to the users in turn (a user that cannot make one passes it on). The validation
    users get one spec per question type (`one_each`). Deterministic for the same users."""
    catalogue = catalogue or load_batch3_catalogue()
    users = {n: batch3_user(n, catalogue) for n in numbers}
    specs: dict[int, list[Spec]] = {n: [] for n in numbers}
    seen: set[tuple] = set()
    turn = 0
    makers: set = set()
    for want_index, want in enumerate(SQL_WANTS + OTHER_WANTS):
        if one_each and want.maker in makers:
            continue
        makers.add(want.maker)
        for copy in range(1 if one_each else want.count):
            for attempt in range(len(numbers) * 3):
                number = numbers[(turn + attempt) % len(numbers)]
                rng = random.Random(f"{SEED_PREFIX}/{number}/{want_index}/{copy}/{attempt}")
                spec = want.maker(users[number], rng, *want.args)
                key = (number, spec.template, spec.target, spec.description) if spec else None
                if spec is not None and key not in seen:
                    seen.add(key)
                    specs[number].append(spec)
                    break
            turn += 1
    return specs
