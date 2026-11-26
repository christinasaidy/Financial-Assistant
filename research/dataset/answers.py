"""Batch 5 part 2: the answer sentences (approved by Christina on 2026-11-19).

After the query runs, the app sends a second prompt (build_answer_prompt: the question, the result rows and totals) and
the model writes the sentence the user sees. No example had ever taught that. These are her patterns, one per kind of
result, filled from the real result of each question: English, and Arabizi in the man's, the woman's or the neutral
form (no "you"). Her rules:
- money as $12.50 and 1,450,000 LBP; "about" is "ya3ne ta2riban"; dates as 9 December 2026;
- once / twice / 3+: "marra wa7de", "martain", "{n} marrat"; quantities 1 and 2 in words ("wa7de", "tnen");
- the answer repeats the item and the period, in the user's own words from the question ("khebez", "hal shaher");
- only numbers that are in the result (the app's own number check refuses any other).
A result of a kind with no pattern gives no answer example.
"""

import random
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.domain.assistant.prompt import Gender

from research.dataset.checks import contains

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")  # fmt: skip


@dataclass(frozen=True)
class Asked:
    """What the answer may repeat: the question's own words for the item, shop and period, and the user's gender."""

    question: str
    arabizi: bool
    gender: Gender
    item: str = ""  # as the user wrote it (Arabizi) or its name (English)
    shop: str = ""
    period: str = ""  # her phrase (Arabizi) or in plain English; "" when the question names none or it has no phrase
    bill: bool = False  # the item is a bill or subscription (never counted as bought)


# --- numbers, dates and counts, as she writes them ---


def money(currency: str, value) -> str:
    amount = Decimal(str(value))
    if currency == "LBP":
        return f"{int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP)):,} LBP"
    return f"${amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"


def usd(value) -> str:
    return money("USD", value)


def day(value) -> str:
    when = value.date() if isinstance(value, datetime) else value
    if isinstance(when, str):
        when = date.fromisoformat(when[:10])
    return f"{when.day} {MONTHS[when.month - 1]} {when.year}"


def month(value) -> str:
    when = value.date() if isinstance(value, datetime) else date.fromisoformat(str(value)[:10])
    return f"{MONTHS[when.month - 1]} {when.year}"


def times_ar(n: int) -> str:
    return "marra wa7de" if n == 1 else "martain" if n == 2 else f"{n} marrat"


def based_on(n: int) -> str:
    """How many purchases a compared price comes from: unsaid for one, "(7asab 3 marrat)" for more (approved)."""
    return "" if n == 1 else f" (7asab {times_ar(n)})"


def times_en(n: int) -> str:
    return "once" if n == 1 else "twice" if n == 2 else f"{n} times"


def count_ar(n) -> str:
    n = Decimal(str(n))
    return "wa7de" if n == 1 else "tnen" if n == 2 else _plain(n)


def _plain(n: Decimal) -> str:
    """A number as a person writes it: at most 2 decimals, no trailing zeros (2.5, 0.3, 14)."""
    rounded = Decimal(str(n)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize()
    return format(rounded, "f")


def receipts_ar(n: int) -> str:
    return "fatoura wa7de" if n == 1 else "fatourtain" if n == 2 else f"{n} fwatir"


# --- the user's own words ---


def own_word(question: str, words) -> str:
    """The longest of `words` the question contains, as written there; "" if none."""
    for word in sorted({w for w in words if w}, key=len, reverse=True):
        found = re.search(rf"(?<!\w){re.escape(word)}(?!\w)", question, re.IGNORECASE)
        if found:
            return found.group(0)
    return ""


# Her period phrases (grammar notes), rotated; any other period is left unsaid in an Arabizi answer.
ARABIZI_PERIODS = {
    "this_month": ("hal shaher", "he el shaher", "hayda el shaher"),
    "last_month": ("el shaher el madi", "ekher shaher", "el shaher li ata3"),
    "this_week": ("hal jem3a", "he el jem3a"), "last_week": ("el jem3a li mar2it", "ekher jem3a"),
    "yesterday": ("mbere7",), "today": ("lyom",), "this_year": ("hal sene", "hay el sene"),
    "since_start_of_year": ("hal sene", "mn awal el sene"), "last_year": ("el sene el madye",),
    "weekend": ("el weekend",),
}  # fmt: skip


def arabizi_period(kind: str, question: str, rng: random.Random) -> str:
    """Her phrase for the period: the one the question uses if it is one of hers, otherwise one of them."""
    if kind.startswith("month_") and kind.removeprefix("month_").isdigit():
        return f"bi {MONTHS[int(kind.removeprefix('month_')) - 1]}"
    phrases = ARABIZI_PERIODS.get(kind, ())
    return own_word(question, phrases) or (rng.choice(phrases) if phrases else "")


def english_period(description: str) -> str:
    """A period's plain English phrase from its description: "last month (the previous calendar month)" -> "last
    month", "the last 30 days (...)" -> "in the last 30 days"."""
    phrase = description.split(" (", 1)[0].strip()
    if phrase.startswith("the weekend"):
        return "at " + phrase
    if phrase.startswith(("the last", "the summer")):
        return "in " + phrase
    return phrase


# --- the verbs she approved, by gender ---

VERBS = {  # man, woman
    "spent": ("sarafet", "sarafte"), "paid": ("dafa3et", "dafa3te"), "bought": ("jebet", "jebte"),
    "ate": ("akalet", "akalte"), "went": ("rehet", "rehte"), "took": ("akhadt", "akhadte"),
    "have": ("3endak", "3endik"), "pay_usually": ("btedfa3", "btedfa3e"), "go_usually": ("trou7", "trou7i"),
}  # fmt: skip


def verb(name: str, gender: Gender) -> str:
    man, woman = VERBS[name]
    return woman if gender is Gender.WOMAN else man


def _spend_verb(question: str) -> str:
    return "paid" if re.search(r"daf|def|dfa", question, re.IGNORECASE) else "spent"


def _buy_verb(question: str) -> str:
    if re.search(r"(?<!\w)(akal|2akal|akalt|akalet)", question, re.IGNORECASE):
        return "ate"
    if re.search(r"(rkeb|akhad|akhd|talab)", question, re.IGNORECASE):
        return "took"
    return "bought"


def _join(parts: list[str], arabizi: bool) -> str:
    if len(parts) < 2:
        return "".join(parts)
    return ", ".join(parts[:-1]) + (" w " if arabizi else " and ") + parts[-1]


def _tail(*words: str) -> str:
    return "".join(f" {w}" for w in words if w)


# --- the layouts and their patterns ---


def layout(columns) -> str | None:
    cols = tuple(columns)
    known = {
        ("currency", "total_spent", "total_spent_usd"): "total",
        ("times",): "times", ("visits",): "visits", ("receipt_count",): "receipts", ("quantity_bought",): "quantity",
        ("last_time",): "last time", ("total_spent_usd",): "usd",
        ("receipt_date", "vendor", "currency", "price", "size_amount", "size_unit"): "last price",
        ("currency", "size_amount", "size_unit", "purchase_count", "average_price", "lowest_price",
         "highest_price"): "average",
        ("month", "currency", "total_spent", "total_spent_usd"): "months",
        ("vendor", "total_spent_usd"): "top shop money", ("vendor", "visits"): "top shop visits",
        ("category", "currency", "total_spent", "total_spent_usd"): "categories",
        ("category", "total_spent_usd"): "top categories", ("receipt_date", "vendor"): "dates",
        ("this_month_usd", "last_month_usd", "percent_change"): "percent",
        ("visits", "visits_per_month"): "how often", ("first_bought", "times"): "since when",
        ("receipt_date", "vendor", "item_name", "currency", "line_total"): "list",
        ("currency", "usual_per_month", "usual_per_month_usd"): "usual",
        ("currency", "latest_date", "latest_price", "previous_date", "previous_price", "percent_change"): "change",
    }  # fmt: skip
    if cols in known:
        return known[cols]
    if len(cols) == 4 and cols[:3] == ("receipt_date", "vendor", "currency") and cols[3].startswith("price_per_"):
        return "last per"
    if len(cols) == 5 and cols[:2] == ("currency", "purchase_count") and cols[2].startswith("average_price_per_"):
        return "average per"
    if len(cols) == 2 and cols[1] == "purchases_without_size":
        return "amount"
    if cols[:3] == ("vendor", "currency", "purchase_count") and len(cols) == 4:
        return "compare"
    if cols[:3] == ("brand", "currency", "purchase_count") and len(cols) == 4:
        return "brands"
    return None


UNITS = {"kilo": ("kilo", "kg"), "litre": ("litre", "l"), "100": ("100 g", "100 g"), "piece": ("wa7de", "piece")}


def _per(column: str) -> str:
    return next((name for name in UNITS if column.endswith(name)), "")


def render(kind: str, columns, rows, asked: Asked, rng: random.Random) -> str | None:
    """The answer for a result of this kind, or None when the result does not fit the pattern."""
    ar, g = asked.arabizi, asked.gender
    neutral = g is Gender.NOT_GIVEN
    item, shop, period = asked.item, asked.shop, asked.period
    thing = item or shop
    r0 = rows[0]

    if kind == "total":
        if all(Decimal(str(amount)) == 0 for _, amount, _ in rows):
            return None  # nothing spent: no approved wording yet
        parts = [money(c, amount) for c, amount, _ in rows]
        about = sum((Decimal(str(u)) for *_, u in rows), Decimal(0))
        if ar:
            amounts = _join(parts, True)
            extra = (f" (ya3ne ta2riban {usd(r0[2])})" if len(rows) == 1 and r0[0] == "LBP" else
                     f", ya3ne ta2riban {usd(about)} bel majmou3" if len(rows) > 1 else "")  # fmt: skip
            where = f"{'la' if shop else '3al'} {thing}" if thing else ""
            if neutral:
                return f"El masruf{_tail(('3a ' + thing) if thing else '', period)}: {amounts}{extra}."
            return f"{verb(_spend_verb(asked.question), g).capitalize()} {amounts}{extra}{_tail(where, period)}."
        amounts = _join(parts, False)
        extra = (f" (about {usd(r0[2])})" if len(rows) == 1 and r0[0] == "LBP" else
                 f", about {usd(about)} in total" if len(rows) > 1 else "")  # fmt: skip
        where = f"{'at' if shop else 'on'} {thing}" if thing else ""
        return f"You spent {amounts}{extra}{_tail(where, period)}."

    if kind in ("times", "visits"):
        n = int(r0[0])
        if n == 0 or (kind == "times" and asked.bill):
            return None  # never (no approved wording yet), or a bill counted as bought
        if ar:
            if kind == "visits" or (shop and not item):
                if neutral:
                    return f"{times_ar(n).capitalize()} 3a {thing}{_tail(period)}." if thing else None
                return f"{verb('went', g).capitalize()} 3a {thing} {times_ar(n)}{_tail(period)}."
            v = _buy_verb(asked.question)
            if neutral:
                return f"{times_ar(n).capitalize()}{_tail(period)}."
            return f"{verb(v, g).capitalize()}{_tail(item)} {times_ar(n)}{_tail(period)}."
        if kind == "visits" or (shop and not item):
            return f"You went to {thing} {times_en(n)}{_tail(period)}." if thing else None
        return f"You bought {item} {times_en(n)}{_tail(period)}." if item else None

    if kind == "receipts":
        n = int(r0[0])
        if n == 0:
            return None
        restaurants = any(w in asked.question.lower() for w in ("mat3am", "mata3em", "restaurant"))
        if ar:
            text = receipts_ar(n) + (" mata3em" if restaurants and n > 2 else "")
            if neutral:
                return f"Fi {text}{_tail(period)}."
            return f"{verb('have', g).capitalize()} {text}{_tail(period)}."
        what = f"{'restaurant ' if restaurants else ''}receipt{'s' if n != 1 else ''}"
        return f"You have {n} {what}{_tail(('from ' + period) if period in ('yesterday', 'today') else period)}."

    if kind == "quantity":
        n = Decimal(str(r0[0]))
        if n == 0 or asked.bill:
            return None
        if ar:
            if neutral:
                return f"{count_ar(n).capitalize()}{_tail(item, period)}."
            return f"{verb('bought', g).capitalize()} {count_ar(n)}{_tail(item, period)}."
        return f"You bought {_plain(n)}{_tail(item, period)}."

    if kind == "last time":
        when = day(r0[0])
        if ar:
            if neutral:
                return f"Ekher marra kenet bi {when}."
            return f"Ekher marra {verb(_buy_verb(asked.question) if item else 'went', g)}{_tail(item or ('3a ' + shop if shop else ''))} kenet bi {when}."  # noqa: E501
        what = f"bought {item}" if item else f"went to {shop}" if shop else "did"
        return f"The last time you {what} was on {when}."

    if kind == "last price":
        when, vendor, currency, price = day(r0[0]), r0[1], r0[2], money(r0[2], r0[3])
        if ar:
            if neutral:
                return f"Ekher marra: {when} mn {vendor}, b {price}."
            return f"Ekher marra {verb('bought', g)}{_tail(item)} kenet bi {when} mn {vendor}, b {price}."
        return f"The last time you bought {item or 'it'} was on {when} at {vendor}, for {price}."

    if kind == "last per":
        unit = _per(columns[3])
        word = UNITS[unit][0]
        when, vendor, price = day(r0[0]), r0[1], money(r0[2], r0[3])
        if ar:
            return f"Ekher marra ({when}, {vendor}), {word}{_tail('el ' + item if item else '')} tole3 b {price}."
        return f"The last time, on {when} at {vendor}, {item or 'it'} cost you {price} a {word if unit != 'piece' else 'piece'}."  # noqa: E501

    if kind == "average":
        def size(row) -> str:
            return f"{_plain(Decimal(str(row[1])))} {row[2]}" if row[1] is not None and row[2] else ""

        if len(rows) == 1:
            currency, _, _, n, avg, low, high = r0
            sized = f" ({size(r0)})" if size(r0) else ""
            if int(n) == 1:
                if ar:
                    if neutral:
                        return f"{(item or 'Hayda')[0].upper() + (item or 'Hayda')[1:]}{sized}{_tail(period)}: marra wa7de b {money(currency, avg)}."
                    return f"{verb('bought', g).capitalize()}{_tail(item)}{sized} marra wa7de{_tail(period)}, b {money(currency, avg)}."
                return f"You bought {item or 'it'}{sized} once{_tail(period)}, for {money(currency, avg)}."
            if ar:
                lead = "Bel 3ade" if neutral else f"Bel 3ade {verb('paid', g)}"
                return (f"{lead} {money(currency, avg)}{_tail(item and ('3al ' + item))}{sized} (mn {money(currency, low)} "
                        f"la {money(currency, high)}), 3ala {times_ar(int(n))}{_tail(period)}.")  # fmt: skip
            return (f"You usually paid {money(currency, avg)} for {item or 'it'}{sized} (from {money(currency, low)} to "
                    f"{money(currency, high)}), over {int(n)} purchases{_tail(period)}.")  # fmt: skip
        sized_rows = [r for r in rows if size(r)][:3]
        if len(sized_rows) < 2:
            return None
        if ar:
            parts = [f"{size(r)} b {money(r[0], r[4])} ({times_ar(int(r[3]))})" for r in sized_rows]
            if neutral:
                return f"{(item or 'Hayda')[0].upper() + (item or 'Hayda')[1:]}{_tail(period)}: {_join(parts, True)}."
            return f"{verb('bought', g).capitalize()}{_tail(item)} {_join(parts, True)}{_tail(period)}."
        parts = [f"{size(r)} at {money(r[0], r[4])} ({int(r[3])} purchase{'s' if int(r[3]) != 1 else ''})"
                 for r in sized_rows]  # fmt: skip
        return f"You bought {item or 'it'} in {_join(parts, False)}{_tail(period)}."

    if kind == "average per":
        currency, n, avg, low, high = r0
        unit = _per(columns[2])
        word = UNITS[unit][0]
        if ar:
            if int(n) == 1:
                lead = "" if neutral else f"{verb('paid', g).capitalize()} "
                text = f"{lead}{money(currency, avg)} la kel {word}{_tail(item and ('3al ' + item), period)}."
                return text[0].upper() + text[1:]
            lead = "Bel 3ade" if neutral else f"Bel 3ade {verb('paid', g)}"
            return (f"{lead} {money(currency, avg)} la kel {word}{_tail(item and ('3al ' + item))} (mn {money(currency, low)} "
                    f"la {money(currency, high)}), 3ala {times_ar(int(n))}{_tail(period)}.")  # fmt: skip
        if int(n) == 1:
            return f"You paid {money(currency, avg)} a {word} for {item or 'it'}{_tail(period)} (1 purchase)."
        return (f"You usually paid {money(currency, avg)} a {word} for {item or 'it'} (from {money(currency, low)} to "
                f"{money(currency, high)}), over {int(n)} purchases{_tail(period)}.")  # fmt: skip

    if kind == "amount":
        value, missing = r0
        if value is None:
            return None
        unit = {"kilos": ("kilo", "kg"), "litres": ("litre", "l"), "pieces": ("", ""), "dozens": ("dazine", "dozen")}[columns[0]]
        amount = _plain(Decimal(str(value)))
        if ar:
            text = f"{amount}{_tail(unit[0], item, period)}"
            body = text if neutral else f"{verb('bought', g).capitalize()} {text}"
            note = f", w fi {receipts_ar(int(missing))} ma fiha wazn, ma 7asabton" if missing else ""
            return f"{body[0].upper() + body[1:]}{note}."
        note = f" ({int(missing)} purchase{'s' if int(missing) != 1 else ''} with no size printed are not counted)" if missing else ""
        return f"You bought {amount}{_tail(unit[1] + (' of' if unit[1] else ''), item, period)}{note}."

    if kind in ("compare", "brands"):
        rows = sorted(rows, key=lambda r: Decimal(str(r[3])))  # cheapest first, whatever order the query gave

    if kind == "compare":
        if (len(rows) < 2 or len({r[1] for r in rows}) > 1 or len({r[0] for r in rows}) < len(rows)
                or Decimal(str(rows[0][3])) == Decimal(str(rows[1][3]))):
            return None  # prices in two currencies cannot be compared, and a tie is not cheaper
        unit = _per(columns[3]) or ""
        per_ar = f" la kel {UNITS[unit][0]}" if unit else ""
        per_en = f" per {UNITS[unit][1]}" if unit else ""
        best, *others = rows
        if ar:
            rest = _join([f"{r[0]} {money(r[1], r[3])}{based_on(int(r[2]))}" for r in others[:2]], True)
            return f"{best[0]} arkhas: {money(best[1], best[3])}{per_ar}{based_on(int(best[2]))}, w {rest}."
        rest = _join([f"{money(r[1], r[3])} at {r[0]} ({int(r[2])} purchase{'s' if int(r[2]) != 1 else ''})" for r in others[:2]], False)  # noqa: E501
        return f"{best[0]} was cheaper for you: {money(best[1], best[3])}{per_en} ({int(best[2])} purchase{'s' if int(best[2]) != 1 else ''}), against {rest}."  # noqa: E501

    if kind == "brands":
        if (len(rows) < 2 or len({r[1] for r in rows}) > 1 or rows[0][0] == rows[1][0]
                or Decimal(str(rows[0][3])) == Decimal(str(rows[1][3]))):
            return None
        unit = _per(columns[3]) or ""
        per_ar = f" la kel {UNITS[unit][0]}" if unit else ""
        per_en = f" per {UNITS[unit][1]}" if unit else ""
        best, second = rows[0], rows[1]
        name = lambda b: b[:1].upper() + b[1:]  # noqa: E731
        if ar:
            return (f"{name(best[0])} arkhas: {money(best[1], best[3])}{per_ar}{based_on(int(best[2]))}, ba3da "
                    f"{name(second[0])} b {money(second[1], second[3])}{based_on(int(second[2]))}.")  # fmt: skip
        return (f"{name(best[0])} was the cheapest for you: {money(best[1], best[3])}{per_en} ({int(best[2])} purchase"
                f"{'s' if int(best[2]) != 1 else ''}), then {name(second[0])} at {money(second[1], second[3])} "
                f"({int(second[2])} purchase{'s' if int(second[2]) != 1 else ''}).")  # fmt: skip

    if kind == "months":
        by_month: dict[str, list[str]] = {}
        for m, currency, amount, _ in rows:
            by_month.setdefault(month(m), []).append(money(currency, amount))
        if len(by_month) != 2:
            return None
        (first, a), (second, b) = by_month.items()
        usd_of = {}
        for m, currency, amount, u in rows:
            usd_of[month(m)] = usd_of.get(month(m), Decimal(0)) + Decimal(str(u))
        more_first = usd_of[first] > usd_of[second]
        if ar:
            spent = "" if neutral else f" {verb('spent', g)}"
            return (f"Bi {first}{spent} {_join(a, True)}, w bi {second} {_join(b, True)}, ya3ne "
                    f"{first if more_first else second} kan aktar.")  # fmt: skip
        return f"In {first} you spent {_join(a, False)}; in {second}, {_join(b, False)}, so {first if more_first else second} was more."  # noqa: E501

    if kind == "top shop money":
        vendor, total = r0
        if ar:
            if neutral:
                return f"Aktar ma7al{_tail(period)}: {vendor}, b {usd(total)}."
            return f"Aktar ma7al {verb(_spend_verb(asked.question), g)} fi kan {vendor}{_tail(period)}: {usd(total)}."
        return f"You spent the most at {vendor}{_tail(period)}: {usd(total)}."

    if kind == "top shop visits":
        vendor, visits = r0
        if ar:
            lead = "Aktar ma7al" if neutral else f"Aktar ma7al {verb('went', g)} 3le"
            return f"{lead}{_tail(period)}: {vendor} ({times_ar(int(visits))})."
        return f"The shop you went to most{_tail(period)} was {vendor} ({int(visits)} visit{'s' if int(visits) != 1 else ''})."

    if kind in ("categories", "top categories"):
        totals: dict[str, list[str]] = {}
        combined: dict[str, Decimal] = {}
        for row in rows:
            name = row[0]
            if name == "Tax, discounts & rounding":
                continue
            totals.setdefault(name, []).append(usd(row[1]) if kind == "top categories" else money(row[1], row[2]))
            combined[name] = combined.get(name, Decimal(0)) + Decimal(str(row[1] if kind == "top categories" else row[3]))
        # largest first by the category's combined USD (LBP and USD rows of one category together)
        named = sorted(totals.items(), key=lambda kv: -combined[kv[0]])[:3]
        if not named:
            return None
        parts = [f"{n} ({_join(v, ar)})" for n, v in named]
        if kind == "top categories":
            if ar:
                return f"Aktar {len(named)} categories{_tail(period)}: {_join(parts, True)}."
            return f"Your top {len(named)} were {_join(parts, False)}{_tail(period)}."
        total = sum((Decimal(str(row[3])) for row in rows), Decimal(0))
        if ar:
            first, *rest = parts
            more = f", ba3da {_join(rest, True)}" if rest else ""
            lead = f"{period[0].upper() + period[1:]}, aktar" if period else "Aktar"
            return f"{lead} shi ra7o 3al {first}{more}, ya3ne ta2riban {usd(total)} bel majmou3."
        first, *rest = parts
        more = f", then {_join(rest, False)}" if rest else ""
        return f"Most went to {first}{more}, about {usd(total)} in total{_tail(period)}."

    if kind == "dates":
        days = [r[0] for r in rows]
        if len({(d.year, d.month) for d in days}) == 1:
            listed = _join([str(d.day) for d in days[:6]], ar) + f" {MONTHS[days[0].month - 1]} {days[0].year}"
        else:
            listed = _join([day(d) for d in days[:4]], ar)
        vendor = rows[0][1]
        if ar:
            if neutral:
                return f"{vendor}: {listed}."
            v = _buy_verb(asked.question)
            v = "took" if v == "took" else "went"
            return f"{verb(v, g).capitalize()} {'' if v == 'took' else '3a '}{vendor} bi {listed}."
        return f"You went to {vendor} on {listed}."

    if kind == "percent":
        this, last, change = r0
        pct = abs(Decimal(str(change)))
        word_ar, word_en = ("a2al", "less") if Decimal(str(change)) < 0 else ("aktar", "more")
        if ar:
            spent = "" if neutral else f" {verb('spent', g)}"
            return f"Hal shaher{spent} {usd(this)}, w el shaher el madi {usd(last)}: ya3ne {_plain(pct)}% {word_ar}."
        return f"This month you've spent {usd(this)}, against {usd(last)} last month: {_plain(pct)}% {word_en}."

    if kind == "how often":
        visits = int(r0[0])
        if visits == 0:
            return None
        if ar:
            if neutral:
                return f"{times_ar(visits).capitalize()} bel 3 eshor el ekhrin{_tail('3a ' + shop if shop else '')}."
            return f"{verb('went', g).capitalize()}{_tail('3a ' + shop if shop else '')} {times_ar(visits)} bel 3 eshor el ekhrin."
        return f"You went to {shop or 'it'} {times_en(visits)} in the last 3 months."

    if kind == "since when":
        first, n = r0
        if ar:
            if neutral:
                return f"Awal marra: {day(first)}, w {times_ar(int(n))} men wa2ta."
            v = verb(_buy_verb(asked.question), g)
            return f"Awal marra {v}{_tail(item)} kenet bi {day(first)}, w {v} {times_ar(int(n))} men wa2ta."
        return f"You first bought {item or 'it'} on {day(first)}, and {times_en(int(n))} in all since then."

    if kind == "list":
        by_shop: dict[str, list[str]] = {}
        for _, vendor, name, currency, amount in rows[:6]:
            by_shop.setdefault(vendor, []).append(f"{name} ({money(currency, amount)})")
        if ar:
            parts = [f"{_join(things, True)} mn {vendor}" for vendor, things in by_shop.items()]
            lead = "" if neutral else f"{verb('bought', g)} "
            text = f"{_tail(period).strip().capitalize() + ': ' if neutral and period else ''}{lead}{_join(parts, True)}"
            return text[0].upper() + text[1:] + "."
        parts = [f"{_join(things, False)} at {vendor}" for vendor, things in by_shop.items()]
        return f"You bought {_join(parts, False)}{_tail(period)}."

    if kind == "usual":
        about = sum((Decimal(str(r[2])) for r in rows), Decimal(0))
        parts = _join([money(r[0], r[1]) for r in rows], ar)
        split = f": {parts}" if len(rows) > 1 or rows[0][0] == "LBP" else ""
        if ar:
            lead = "Bel 3ade" if neutral else f"Bel 3ade {verb('pay_usually', g)}"
            return f"{lead} ta2riban {usd(about)} bel shaher{_tail(item and ('3al ' + item))}{split}."
        return f"You usually spend about {usd(about)} a month on {item or 'it'}{split}."

    if kind == "change":
        currency, latest_d, latest_p, prev_d, prev_p, change = r0
        if change is None or prev_p is None or Decimal(str(change)) == 0:
            return None
        pct = abs(Decimal(str(change)))
        up = Decimal(str(change)) > 0
        if ar:
            lead = f"Eh, zed {_plain(pct)}%" if up else f"La2, no2is {_plain(pct)}%"
            return f"{lead}: {money(currency, latest_p)} bi {day(latest_d)}, w ken {money(currency, prev_p)} bi {day(prev_d)}."
        lead = f"Yes, it went up {_plain(pct)}%" if up else f"No, it went down {_plain(pct)}%"
        return f"{lead}: {money(currency, latest_p)} on {day(latest_d)}, against {money(currency, prev_p)} on {day(prev_d)}."

    if kind == "usd":
        (total,) = r0
        if ar:
            if neutral:
                return f"El masruf{_tail(period)}: {usd(total)}."
            return f"{verb('spent', g).capitalize()} {usd(total)}{_tail(period)}."
        return f"You spent {usd(total)}{_tail(period)}."
    return None
