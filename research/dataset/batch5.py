"""Batch 5 part 1: chat jobs (decided with Christina on 2026-11-17/19; agent_documentation/PROGRESS.md).

Each job is a short chat on one batch-3/4 user. It starts with a question she already reviewed (with its own gold
reply) and adds one or two new user turns that I write and she reviews. The new last turn is what the example
teaches:

- A, a topic change that looks like a follow-up ("tab w ...", "ok w ...", "merci, w ...", a shop of the same kind,
  an item of the same kind): it names its own item or shop and period, so nothing carries over (uses no history);
- B, the answer to the assistant's clarifying question ("mn 1 la 10 hal shaher", "eh laban", "kanoun el tene");
- C, the same question with another measure ("w kam mara?", "w aday dafa3et 3leh?", "w aymta ekher mara?");
- D, a correction of the item or shop ("la2, azde el feta"), or of a period carried over from the first question
  ("tab w 3al manakish?" -> "la2, ekher shaher"), and the same carried-over chat accepted with thanks;
- E, a filter taken away ("w bel majmou3, msh bas X?", "w men awal ma sajjalet fwatir?").

Every target is built from the first question's own SQL and the same SQL pieces the batches use (templates.money,
item_is, ...), so a follow-up answer looks exactly like a standalone one. The first question's period is reused only
when its SQL, rebuilt from its pieces, is exactly its gold SQL.

Each job gets 4 versions: 3 Arabizi/mixed and 1 English, each on a different stored version of the first question.
The versions of a clarified question (B) ask different things ("shu dafa3et bi Malak?", "kam marra akalt men Malak
hal shaher?"), so a B turn offers several correct answers (`options`) and each version names the one its question
asks for; a version that fits none is not used.
"""

import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

from research.dataset import batch3, batch4, periods, templates
from research.dataset.templates import UserData, item_is, money, quoted

DATA_DIR = Path(__file__).parent / "data"
SEED = "fyp-dataset/batch5-part1"
TRAIN = (*batch3.TRAIN, *batch4.TRAIN)
VALIDATION = (*batch3.VALIDATION, *batch4.VALIDATION)
TODAYS = {**batch3.TODAYS, **batch4.TODAYS}
# Jobs per kind (approved 2026-11-17/19): about 160, 140 training and 20 validation.
COUNTS = {"train": {"A": 61, "B": 35, "C": 17, "D": 20, "E": 7}, "validation": {"A": 9, "B": 5, "C": 3, "D": 2, "E": 1}}
LEAD_INS = ("w", "tab w", "bas", "merci, w", "ok w")
# Items a user may mean instead of another ("la2, azde el feta" after cheese): a correction stays inside one of these
# or inside a catalogue group (clothes, snacks, cleaning, ...).
CONFUSED = ({"cheese", "feta", "mozzarella", "halloumi", "labneh"}, {"meat", "minced meat", "steak", "kafta"},
            {"chicken", "whole chicken", "tawouk"}, {"coffee", "cappuccino", "latte", "espresso", "iced coffee"},
            {"biscuits", "digestive biscuits", "maamoul"}, {"juice", "fresh juice", "iced tea", "soda"},
            {"bread", "kaak", "croissant", "manakish"}, {"chocolate", "chocolate spread", "brownies", "cake"},
            {"water", "soda", "juice"}, {"shampoo", "conditioner", "shower gel", "soap"},
            {"tea", "iced tea"}, {"oil", "olive oil", "ghee"}, {"rice", "bulgur", "lentils", "pasta", "spaghetti"},
            {"taxi ride", "fuel"}, {"cigarettes", "tobacco sticks", "argile"})  # fmt: skip
# Her thanks replies (small_talk_reviewed.md): none of them changes with gender.
THANKS_REPLIES = ("Ahla w Sahla", "Walaw", "Ya Hala", "Ta3a kel yom", "3a rasi")
ENGLISH_THANKS = ("You're welcome!", "Anytime!", "Glad I could help!")


@dataclass(frozen=True)
class NewTurn:
    """A user turn I write, and what the assistant answers."""

    description: str  # what the user says, in plain English, for the writer (me) and the reviewer (her)
    target: str  # the SQL, or REPLY: ... (Arabizi) for thanks
    kind: str = "sql"
    english_target: str | None = None  # a REPLY's English text, for the English version
    labels: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)  # B: the correct answer for each thing the first question may ask


@dataclass(frozen=True)
class ChatJob:
    job_id: str  # b5-<user>-<index>
    user: int
    split: str
    kind: str  # A, B, C, D or E
    sub: str  # what kind of A, B, ... (for the report and the review)
    first_spec: str  # the stored question the chat starts with
    first_versions: tuple[tuple[str, str], ...]  # (language, question) of every stored version, to choose from
    turns: tuple[NewTurn, ...]
    role: str  # "independent" (the last turn needs no history) or "dependent"


@dataclass(frozen=True)
class Stored:
    """A reviewed batch-3/4 question: its versions and what its SQL is made of."""

    spec: str
    user: int
    template: str
    kind: str
    labels: dict
    target: str  # the gold of its versions (the SQL; for CLARIFY the Arabizi reply of its first Arabizi version)
    versions: tuple[tuple[str, str], ...]  # (language, question)
    view: str = ""
    what: str = ""  # item_name = '...' or vendor = '...' ("" for none)
    period: str = ""  # the period condition exactly as written in the gold ("" for none)
    dates: periods.Period | None = None  # the same period with its days, when its label names it


RAW_DIR = Path(__file__).parent / "raw"


def _descriptions(raw_dir: Path = RAW_DIR) -> dict[str, str]:
    """What each batch-3/4 question was written to ask (its spec's description), by spec id."""
    found = {}
    for batch in ("batch3", "batch4"):
        for chunk in sorted((raw_dir / batch / "jobs").glob("*.jsonl")):
            for line in chunk.read_text(encoding="utf-8").splitlines():
                job = json.loads(line)
                found[job["spec_id"]] = job["spec"]["description"]
    return found


def load_stored(data_dir: Path = DATA_DIR, raw_dir: Path = RAW_DIR) -> dict[int, list[Stored]]:
    """The reviewed questions of every batch-3/4 user, by user. A clarified period question about one item's price or
    one place's visits is marked about_item: its answer would need that item, which its labels do not hold."""
    descriptions = _descriptions(raw_dir)
    rows = defaultdict(list)
    for batch in ("batch3", "batch4"):
        for split in ("train", "validation"):
            for line in (data_dir / batch / f"{split}.jsonl").read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                rows[row["labels"]["spec"]].append(row)
    found = defaultdict(list)
    for spec, versions in rows.items():
        first = versions[0]
        labels = first["labels"]
        question = [(r["labels"]["language"], r["messages"][0]["content"].rsplit("Question: ", 1)[1].removesuffix(
            "\nReply:")) for r in versions]  # fmt: skip
        arabizi = next((r for r in versions if r["labels"]["language"] != "english"), first)
        about = descriptions.get(spec, "")
        if labels["template"] == "C4" and ("for an item" in about or "went somewhere" in about):
            labels = {**labels, "about_item": True}
        stored = Stored(spec, labels["user"], labels["template"], labels["kind"], labels,
                        arabizi["messages"][1]["content"], tuple(question))  # fmt: skip
        found[stored.user].append(_pieces(stored))
    return found


_SHAPES = {  # template: (view, how its SQL is built from (what, period))
    "T9": ("purchases", lambda w, p: money("purchases", "line_total", w, p)),
    "T6": ("receipts", lambda w, p: money("receipts", "total", w, p)),
    "T14": ("purchases", lambda w, p: _times("purchases", "times", w, p)),
    "T8": ("receipts", lambda w, p: _times("receipts", "visits", w, p)),
    "T1": ("receipts", lambda w, p: money("receipts", "total", w, p)),
}


def _times(view: str, name: str, *conditions: str) -> str:
    return f"SELECT COUNT(DISTINCT receipt_id) AS {name} FROM {view}{templates._where(*conditions)}"


def _pieces(stored: Stored) -> Stored:
    """The stored question with its view, what and period, when its gold is exactly rebuilt from them."""
    shape = _SHAPES.get(stored.template)
    if stored.kind != "sql" or shape is None or stored.labels.get("negation"):
        return stored
    view, build = shape
    labels = stored.labels
    what = item_is(labels["item"]) if labels.get("item") else f"vendor = {quoted(labels['shop'])}" if labels.get(
        "shop") else ""  # fmt: skip
    where = re.search(r" WHERE (.*?)(?: GROUP BY .*)?$", stored.target)
    conditions = where.group(1) if where else ""
    period = conditions[len(what):].removeprefix(" AND ") if conditions.startswith(what) else None
    if period is None or build(what, period) != stored.target:
        return stored
    return replace(stored, view=view, what=what, period=period, dates=period_of(str(labels.get("period")),
                                                                                 TODAYS[stored.user], period))


_SIMPLE = {"none": periods.no_period, "this_month": periods.this_month, "last_month": periods.last_month,
           "this_week": periods.this_week, "last_week": periods.last_week, "today": periods.today_period,
           "yesterday": periods.yesterday, "day_before_yesterday": periods.day_before_yesterday,
           "since_yesterday": periods.since_yesterday, "this_year": periods.this_year,
           "since_start_of_year": periods.since_start_of_year, "last_year": periods.last_year,
           "last_few_weeks": periods.last_few_weeks, "since_summer": periods.since_summer, "summer": periods.summer,
           "weekend": periods.weekend}  # fmt: skip
_NUMBERED = {"since_weekday": periods.since_weekday, "weekday": periods.weekday, "month": periods.named_month,
             "since_month": periods.since_month, "last_days": None, "last_weeks": None, "last_months": None}


def period_of(kind: str, today: date, sql: str | None) -> periods.Period | None:
    """The period a label names, with its days, only if its SQL is exactly `sql` (otherwise None); with `sql` None,
    whatever the label names (used for an answer's words, never for SQL)."""
    found = None
    if kind in _SIMPLE:
        found = _SIMPLE[kind](today) if kind != "none" else periods.no_period()
    elif m := re.fullmatch(r"(since_weekday|weekday|month|since_month)_(\d+)", kind):
        found = _NUMBERED[m.group(1)](today, int(m.group(2)))
    elif m := re.fullmatch(r"last_(\d+)_(days|weeks|months|years)", kind):
        maker = {"days": periods.last_days, "weeks": periods.last_weeks, "months": periods.last_months,
                 "years": periods.last_years}[m.group(2)]  # fmt: skip
        found = maker(today, int(m.group(1)))
    return found if found is not None and (sql is None or found.sql == sql) else None


def _bought(data: UserData, period: periods.Period | None, name: str) -> bool:
    """Whether the user bought `name` (an item or a shop) in the period; True when the period is unknown."""
    if period is None:
        return True
    if name in data.shops:
        return any(r.shop == name for r in data.receipts_in(period))
    return bool(data.bought(period, name))


def _prefer_bought(data: UserData, period, names: list[str], rng: random.Random) -> str | None:
    """Mostly one the user bought in the period, as the batches do (templates.IN_PERIOD_SHARE)."""
    bought = [n for n in names if _bought(data, period, n)]
    pool = bought if bought and rng.random() < templates.IN_PERIOD_SHARE else names
    return rng.choice(pool) if pool else None


def _usable(stored: Stored) -> bool:
    return bool(stored.view)


# --- the users' data ---


def user_data(number: int) -> UserData:
    return batch3.batch3_user(number) if number in batch3.TODAYS else batch4.batch4_user(number)


def _item_name(what: str) -> str | None:
    found = re.fullmatch(r"item_name = '((?:[^']|'')*)'", what)
    return found.group(1).replace("''", "'") if found else None


def _shop_name(what: str) -> str | None:
    found = re.fullmatch(r"vendor = '((?:[^']|'')*)'", what)
    return found.group(1).replace("''", "'") if found else None


def _sibling_item(data: UserData, name: str, rng: random.Random, period=None) -> str | None:
    """An item of the same category (for a topic change)."""
    category = data.catalogue.item(name).category
    return _prefer_bought(data, period, [i for i in data.items if i != name and data.catalogue.item(i).category ==
                                         category], rng)  # fmt: skip


def _confused_item(data: UserData, name: str, rng: random.Random, period=None) -> str | None:
    """An item the user could have meant instead (a correction): the same CONFUSED set or catalogue group."""
    group = data.catalogue.item(name).group
    close = set().union(*(s for s in CONFUSED if name in s))
    pool = [i for i in data.items if i != name and (i in close or (group and data.catalogue.item(i).group == group))]
    bought = [i for i in pool if _bought(data, period, i)]  # a correction to something never bought there: none
    return rng.choice(bought) if bought else None


def _sibling_shop(data: UserData, name: str, rng: random.Random, period=None) -> str | None:
    kind = data.shop(name).kind
    return _prefer_bought(data, period, [s for s in data.shops if s != name and data.shop(s).kind == kind], rng)


def _is_bill(data: UserData, name: str) -> bool:
    """A bill or subscription (its item is sold only by named vendors), or a shop that only sends those."""
    if name in data.shops:
        return data.shop(name).kind == "utility" or any(name in i.vendors for i in data.catalogue.items)
    return bool(data.catalogue.item(name).vendors)


def _measure(stored: Stored) -> str:
    return {"T9": "money", "T6": "money", "T1": "money", "T14": "times", "T8": "times"}[stored.template]


def _target(view: str, measure: str, what: str, period: str) -> str:
    if measure == "money":
        return money(view, "total" if view == "receipts" else "line_total", what, period)
    return _times(view, "visits" if view == "receipts" else "times", what, period)


# --- the kinds ---


def _a(data: UserData, first: Stored, rng: random.Random) -> NewTurn | None:
    """A topic change: another item or shop (sometimes of the same kind), its own period, a follow-up's opening."""
    lead = rng.choice(LEAD_INS)
    period = templates._period(data, rng)
    if not period.sql or period.sql == first.period:
        return None
    measure = rng.choice(("money", "times"))
    item, shop = _item_name(first.what), _shop_name(first.what)
    if shop and rng.random() < 0.5:
        other = _sibling_shop(data, shop, rng, period)
        how = "a shop of the same kind"
    elif item and rng.random() < 0.5:
        other = _sibling_item(data, item, rng, period)
        how = "an item of the same kind"
    else:
        other, how = None, "something else"
    if other is None:
        how = "something else"
        other = _prefer_bought(data, period, [s for s in data.shops if s != shop] if shop or rng.random() < 0.4 else
                               [i for i in data.items if i != item], rng)  # fmt: skip
    is_shop = other in data.shops
    if _is_bill(data, other):  # bills and subscriptions are paid once a month: never "how many times" (2026-11-15)
        measure = "money"
    what = f"vendor = {quoted(other)}" if is_shop else item_is(other)
    view = "receipts" if is_shop else "purchases"
    asks = (f"how much they spent {'at' if is_shop else 'on'} {other}" if measure == "money" else
            f"how many times they went to {other}" if is_shop else f"how many times they bought {other}")  # fmt: skip
    return NewTurn(f'Starts with "{lead} ..." but is a new question ({how}): {asks}, {period.description}. Names its '
                   "own period.",
                   _target(view, measure, what, period.sql), labels={"lead_in": lead, "other": other,
                                                                     "period": period.kind})  # fmt: skip


def _b(data: UserData, first: Stored, rng: random.Random, again: bool = False) -> NewTurn | None:
    """The answer to the assistant's clarifying question. A question used a second time (`again`) gets another
    answer: for an unknown item or shop, the user names what they meant instead of taking the suggestion."""
    labels, today = first.labels, data.today
    if first.template in ("C1", "C2") and labels.get("suggestion"):
        is_shop = first.template == "C2"
        if again:  # what they meant instead: a shop of the same kind, or an item they could have meant
            asked = labels.get("shop" if is_shop else "item")
            if is_shop:
                kind = next((s.kind for s in data.catalogue.shops if s.name == asked), None)
                pool = [n for n in data.shops if data.shop(n).kind == kind]
            else:
                group = next((i.group for i in data.catalogue.items if i.name == asked), None)
                close = set().union(*(s for s in CONFUSED if asked in s))
                pool = [n for n in data.items if n in close or (group and data.catalogue.item(n).group == group)]
            pool = [n for n in pool if n != labels["suggestion"]]
            if not pool:
                return None
            name = rng.choice(pool)
            said, answer = f'Says no, they meant {name} ("la2, azde {name}").', f"other: {name}"
        else:
            name = labels["suggestion"]
            said, answer = f'Says yes to the suggestion ("eh", "eh {name}").', "yes"
        options = _named_options(today, f"vendor = {quoted(name)}" if is_shop else item_is(name), is_shop)
        return NewTurn(said, options["money/none"], labels={"answer": answer, "named": name}, options=options)
    if first.template != "C4" or first.labels.get("about_item"):
        return None
    period = str(labels.get("period"))
    if period == "bi awal el shaher":
        last = rng.choice((5, 7, 10))
        month = today.month if today.day > last else (today.replace(day=1) - timedelta(days=1)).month
        p = periods.day_range(today, month, 1, last)
        said = "this month" if month == today.month else "last month"
        options = _period_options(p.sql)
        return NewTurn(f'Answers with the dates: from the 1st to the {last}th of {said} ("mn 1 la {last} ...").',
                       options["total"], labels={"answer": p.kind}, options=options)
    if period == "hal fatra":
        p = rng.choice((periods.last_weeks(today, 2), periods.this_month(today), periods.last_month(today)))
        options = _period_options(p.sql)
        return NewTurn(f"Answers with the period: {p.description}.", options["total"], labels={"answer": p.kind},
                       options=options)  # fmt: skip
    if period == "kanoun":
        month = rng.choice((12, 1))
        p = periods.named_month(today, month)
        return NewTurn(f'Answers which: {"kanoun el awal (December)" if month == 12 else "kanoun el tene (January)"}.',
                       money("receipts", "total", p.sql), labels={"answer": p.kind})
    if period in ("awal el sene", "semester"):
        first_month, last_month = (1, 3) if period == "awal el sene" else rng.choice(((1, 6), (7, 12)))
        p = _months(today, first_month, last_month)
        said = "yes (the first 3 months of the year)" if period == "awal el sene" else (
            f"the months: {periods.MONTHS[first_month - 1]} to {periods.MONTHS[last_month - 1]}")  # fmt: skip
        return NewTurn(f"Answers {said}.", money("receipts", "total", p.sql), labels={"answer": p.kind})
    return None


ASKED_PERIODS = ("none", "this_month", "last_month", "this_week", "last_week", "since_start_of_year")


def _named_options(today: date, what: str, is_shop: bool) -> dict[str, str]:
    """After "eh <name>": how much, how many times, or when last, for each period the first question may have named."""
    view = "receipts" if is_shop else "purchases"
    options = {}
    for kind in ASKED_PERIODS:
        p = periods.no_period() if kind == "none" else _SIMPLE[kind](today)
        options[f"money/{kind}"] = _target(view, "money", what, p.sql)
        options[f"times/{kind}"] = _target(view, "times", what, p.sql)
    options["last time"] = f"SELECT MAX(receipt_date) AS last_time FROM {view} WHERE {what}"
    return options


def _top(where: str) -> str:
    view, condition = where.split("|", 1) if "|" in where else ("receipts", where)
    return (f"SELECT vendor, COUNT(DISTINCT receipt_id) AS visits FROM {view}{templates._where(condition)} "
            "GROUP BY vendor ORDER BY visits DESC LIMIT 1")


def _period_options(period: str) -> dict[str, str]:
    """After the dates are given: the total, or which shop / supermarket / restaurant was visited most (as B2)."""
    return {"total": money("receipts", "total", period), "top shop": _top(period),
            "top supermarket": _top(f"category_spending|category = 'Groceries' AND {period}"),
            "top restaurant": _top(f"category_spending|category = 'Dining' AND {period}")}


def _months(today: date, first: int, last: int) -> periods.Period:
    """From the start of one month to the end of another, the most recent such span that has begun."""
    year = today.year if date(today.year, first, 1) <= today else today.year - 1
    start = date(year, first, 1)
    end = date(year + 1, 1, 1) if last == 12 else date(year, last + 1, 1)
    return periods.Period(f"months_{first}_{last}", f"receipt_date >= '{start}' AND receipt_date < '{end}'", start,
                          end, f"{periods.MONTHS[first - 1]} to {periods.MONTHS[last - 1]}", ())  # fmt: skip


def _c(data: UserData, first: Stored, rng: random.Random) -> NewTurn | None:
    """The same question, another measure."""
    if not first.what:
        return None
    measure = _measure(first)
    if rng.random() < 0.3:
        column = "purchases" if first.view == "purchases" else "receipts"
        return NewTurn('Asks when the last time was ("w aymta ekher mara?").',
                       f"SELECT MAX(receipt_date) AS last_time FROM {column} WHERE {first.what}",
                       labels={"measure": "last time"})  # fmt: skip
    other = "times" if measure == "money" else "money"
    name = _item_name(first.what) or _shop_name(first.what)
    if other == "times" and _is_bill(data, name):
        return None
    said = '"w kam mara?"' if other == "times" else '"w aday dafa3et 3leh?" / "w aday sarafet?"'
    return NewTurn(f"Asks the same thing but {'how many times' if other == 'times' else 'how much'} ({said}).",
                   _target(first.view, other, first.what, first.period), labels={"measure": other})


def _d(data: UserData, first: Stored, rng: random.Random, carried: bool, strict: bool = True
       ) -> tuple[NewTurn, ...] | None:  # fmt: skip
    """A correction of the item or shop, or of a period carried over (corrected, or accepted with thanks). Strict:
    only to an item, shop or period the user bought in (so the corrected answer is not empty); not strict is the
    fallback when no question of a user allows that (the 4 validation users)."""
    period = first.dates if strict else None
    if not first.what or (carried and not first.period):
        return None
    measure = _measure(first)
    item, shop = _item_name(first.what), _shop_name(first.what)
    if not carried:
        other = (_confused_item(data, item, rng, period) if item else
                 _sibling_shop(data, shop, rng, period))  # fmt: skip
        if other is None or not _bought(data, period, other):
            return None
        if other is None:
            return None
        what = item_is(other) if item else f"vendor = {quoted(other)}"
        return (NewTurn(f'Says that is not what they meant: they meant {other} ("la2, azde el {other}", "ken azde '
                        f'{other}", "2asde {other}").', _target(first.view, measure, what, first.period),
                        labels={"correction": "item" if item else "shop", "other": other}),)  # fmt: skip
    if not item:
        return None
    bought = [i for i in data.items if i != item and _bought(data, period, i)]
    if not bought:
        return None
    other = rng.choice(bought)
    if measure == "times" and _is_bill(data, other):  # bills are never counted; a separate draw keeps the plan
        others = [i for i in bought if not _is_bill(data, i)] or [
            i for i in data.items if i != item and not _is_bill(data, i)]
        other = random.Random(f"{SEED}/not-a-bill/{first.spec}").choice(others)
    carried_turn = NewTurn(f'Asks about another item, leaving out the period ("tab w 3al {other}?"): the period of the '
                           f"first question carries over.", _target("purchases", measure, item_is(other), first.period),
                           labels={"carried": "period", "other": other})  # fmt: skip
    if rng.random() < 0.5:
        n = rng.randrange(len(THANKS_REPLIES))
        return carried_turn, NewTurn('Accepts it and thanks ("merci", "tamem merci").', f"REPLY: {THANKS_REPLIES[n]}",
                                     "reply", f"REPLY: {ENGLISH_THANKS[n % len(ENGLISH_THANKS)]}",
                                     labels={"carried": "accepted"})  # fmt: skip
    today = data.today
    said = {"last_month": '"la2, ekher shaher" / "la2, el shaher el madi"', "this_month": '"la2, hal shaher"'}
    choices = [p for p in (periods.last_month(today), periods.this_month(today)) if p.sql != first.period]
    bought = [p for p in choices if data.bought(p, other) or not strict]
    if not bought:
        return None
    p = rng.choice(bought)
    return carried_turn, NewTurn(f"Corrects the period: they meant {p.description} ({said[p.kind]}).",
                                 _target("purchases", measure, item_is(other), p.sql),
                                 labels={"carried": "corrected", "period": p.kind})  # fmt: skip


def _e(data: UserData, first: Stored, rng: random.Random) -> NewTurn | None:
    """A filter taken away: the shop (all spending in the period) or the period (the item since the first receipt)."""
    if first.view == "receipts" and _shop_name(first.what) and first.period and _measure(first) == "money":
        return NewTurn(f'Asks for all their spending, not only at {_shop_name(first.what)} ("w bel majmou3, msh bas '
                       f'{_shop_name(first.what)}?", "w 3a kel el mahallet?").',
                       money("receipts", "total", first.period), labels={"removed": "shop"})  # fmt: skip
    if _item_name(first.what) and first.period:
        return NewTurn('Asks the same for all time, since they started saving receipts ("w men awal ma sajjalet '
                       'fwatir?").', _target(first.view, _measure(first), first.what, ""), labels={"removed": "period"})
    return None


# --- the plan ---


def _versions(stored: Stored, rng: random.Random) -> tuple[tuple[str, str], ...]:
    """Every stored version, in a fixed shuffled order (the writer picks 3 Arabizi/mixed and 1 English)."""
    versions = list(stored.versions)
    rng.shuffle(versions)
    return tuple(versions)


def plan(stored: dict[int, list[Stored]] | None = None) -> list[ChatJob]:
    """All jobs, spread over the users of each split in turn, with fixed seeds."""
    stored = stored or load_stored()
    jobs = []
    for split, users in (("train", TRAIN), ("validation", VALIDATION)):
        rng = random.Random(f"{SEED}/{split}")
        data = {n: user_data(n) for n in users}
        used: dict[tuple[str, str], list[str]] = defaultdict(list)  # (first spec, kind) -> the answers it got
        index = defaultdict(int)
        turn = 0
        for kind, count in COUNTS[split].items():
            made = 0
            for attempt in range(count * 60):
                if made == count:
                    break
                # The user with the most first questions not used yet (then in turn), so a user with few is not
                # asked to start chat after chat from the same question.
                unused = {n: sum(1 for x in stored[n] if _usable(x) and not any(spec == x.spec for spec, _ in used))
                          for n in users}  # fmt: skip
                order = users[turn % len(users):] + users[:turn % len(users)]
                number = max(order, key=lambda n: (unused[n] if kind != "B" else 0, -order.index(n)))
                turn += 1
                strict = attempt < count * 30
                job = _job(kind, data[number], stored[number], rng, used, index[number], split, made, strict)
                if job:
                    jobs.append(job)
                    index[number] += 1
                    made += 1
            if made < count:
                raise ValueError(f"{split}: only {made} of {count} {kind} jobs could be planned")
    return jobs


USES = {"B": 3}  # a question starts at most one chat of a kind; a clarified one three, with different answers


def _job(kind, data, stored, rng, used, index, split, made, strict=True) -> ChatJob | None:
    if kind == "B":
        pool = [s for s in stored if s.template in ("C1", "C2", "C4")]
    else:
        pool = [s for s in stored if _usable(s)]
    uses = {s.spec: sum(len(v) for (spec, _), v in used.items() if spec == s.spec) for s in pool}
    pool = [s for s in pool if len(used[(s.spec, kind)]) < USES.get(kind, 1) and (kind == "B" or uses[s.spec] < 2)
            and any(v[0] == "english" for v in s.versions)]  # fmt: skip
    # Tried in order: the least used first questions first (Christina, 2026-11-19: the same "men nisen" question
    # started three chats; B reuses its few clarified questions on purpose), mostly ones whose answer is not empty.
    keyed = [(0 if kind == "B" else uses[s.spec], 0 if (s.kind != "sql" or s.labels.get("result_rows")) and
              rng.random() < templates.IN_PERIOD_SHARE else 1, rng.random(), s) for s in pool]  # fmt: skip
    for *_, first in sorted(keyed, key=lambda k: k[:3])[:12]:
        job = _chat(kind, data, first, rng, used, index, split, made, strict)
        if job:
            return job
    return None


def _chat(kind, data, first, rng, used, index, split, made, strict) -> ChatJob | None:
    if kind == "A":
        new, sub, role = _a(data, first, rng), "topic change", "independent"
        turns = (new,) if new else None
    elif kind == "B":
        new, role = _b(data, first, rng, again=bool(used[(first.spec, kind)])), "dependent"
        if new and new.labels.get("answer") in used[(first.spec, kind)]:
            new = None  # the same answer twice would be the same chat
        sub, turns = f"answers {first.template}", (new,) if new else None
    elif kind == "C":
        new, sub, role = _c(data, first, rng), "measure", "dependent"
        turns = (new,) if new else None
    elif kind == "D":
        carried = made % 2 == 1  # half item/shop corrections, half carried-over periods
        turns, role = _d(data, first, rng, carried, strict), "dependent"
        sub = "carried period" if carried else "correction"
    else:
        new, sub, role = _e(data, first, rng), "removed filter", "dependent"
        turns = (new,) if new else None
    if not turns:
        return None
    used[(first.spec, kind)].append(turns[-1].labels.get("answer", ""))
    return ChatJob(f"b5-{data.user.number}-{index}", data.user.number, split, kind, sub, first.spec,
                   _versions(first, rng), turns, role)  # fmt: skip
