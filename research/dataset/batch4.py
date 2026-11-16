"""Batch 4 (approved by the user on 2026-11-16, after fine-tune 3's test errors): how questions are SAID, built on new
synthetic users so batches 1-3 stay exactly as they were.

- Users 42-49 train, 50-51 validation, from the catalogue plus the batch-3 and batch-4 extensions.
- Lead-ins before an answerable question ("sert mahwous bi ...", "7eses hale ...", "emme aletle ...", "badi wafir ..."):
  "sert / soret" there means "I have become", not "so far".
- "aday" as a COUNT (aday jebet X = how many), next to "bi aday" (the price) and aday + a money word (spending), in
  sets of four on the same item and period.
- Other verbs and counting words (akalet, shrebet, 3abayt, daharet, 2asayt; 3ed, 3edele, 3adad; 3elbit, sandu2).
- New question kinds: the last time (MAX(receipt_date)), the dates of visits in a period, how often with no period.
- New periods: last year, the last 2 years, the last few weeks, since summer, summer; summaries (tolkhis); greetings
  and sign-offs (REPLY); asking back instead of refusing (CLARIFY), and "bi awal el shaher" (CLARIFY).
- The user's spellings: jebet and shtrit for "I bought", aal / aa next to 3al / 3a (minimums checked in the mix).

Code writes every SQL target; the questions are written for each spec afterwards from the user's seeds
(raw/batch4/seeds.txt).
"""

import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date

from research.dataset import batch3 as b3
from research.dataset import periods
from research.dataset import templates as t
from research.dataset.batch3 import MONTHLY_BILLS, MONTHLY_KINDS, NOT_PRICED
from research.dataset.catalogue import (
    BATCH3_EXTENSION,
    BATCH4_EXTENSION,
    Catalogue,
    load_catalogue,
)
from research.dataset.periods import Period
from research.dataset.templates import Spec, UserData
from research.dataset.users import make_user

SEED_PREFIX = "fyp-dataset/batch4"
# Spread over the year, with four in summer so "since summer" and "this summer" both come up.
TODAYS = {42: date(2026, 4, 8), 43: date(2026, 6, 24), 44: date(2026, 8, 12), 45: date(2026, 9, 30),
          46: date(2026, 12, 9), 47: date(2027, 2, 17), 48: date(2027, 6, 23), 49: date(2027, 9, 8),
          50: date(2026, 7, 15), 51: date(2027, 3, 10)}  # fmt: skip
TRAIN, VALIDATION = tuple(range(42, 50)), (50, 51)

DINING_KINDS = frozenset({"restaurant", "cafe", "fast_food"})

# --- the words every version of a spec must contain (one of each group, in every language) ---

BOUGHT = ("jebet", "jebt", "jibet", "shtrit", "shtarayt", "jebto", "jebta", "jebton", "shtrito", "shtrita", "shtriton",
          "jib", "aam jib", "eshtere", "beshtere", "2eshtere", "bought", "buy", "got", "get")
AS_COUNT = ("aday", "adday", "adde", "adaysh", "addesh", "adesh", "2adesh", "how many")
BI_ADAY = ("bi aday", "b aday", "bi adde", "b adde", "bi adesh", "b adesh", "bi adaysh", "b adaysh", "for how much",
           "what price", "how much did i get")
MONEY = ("dafa3et", "dafa3t", "def3a", "defe3", "defaa", "sarafet", "saraft", "sarfet", "sarafit", "sarfe", "saref",
         "kallaf", "kallafne", "spent", "spend", "paid", "pay")
EAT_DRINK = ("akalet", "akalt", "2akalet", "ekle", "2ekle", "ekel", "shrebet", "shrebt", "shrebta", "shrebto", "ate",
             "eat", "eaten", "drank", "drink", "had")
TIMES = ("mara", "marra", "marat", "marrat", "times", "how often")
GO = ("rehet", "re7et", "ro7t", "rohet", "rehit", "daharet", "dahar", "went", "go", "been", "visited")
FILL = ("3abayt", "3abbet", "3abet", "aabayt", "filled", "fill", "fuel up", "filled up")
CUT = ("2asayt", "asayt", "2assayt", "cut", "haircut")
COUNTING = ("3ed", "3edele", "3eddele", "3adad", "aadad", "count", "number")
UNITS = ("3elbe", "3elbit", "3elbet", "3elab", "kis", "kyes", "sandu2", "sandou2", "can", "cans", "box", "boxes", "pack", "packs", "bottle",
         "bottles", "case", "cases")
LAST_TIME = ("ekher mara", "ekher marra", "akher mara", "last time")
WHEN = ("aymta", "aymata", "emta", "when", "which days", "what dates")
OFTEN = ("3am ru7", "aam ru7", "3am rou7", "aam rou7", "3am ruh", "aam ruh", "3am ro7", "aam ro7", "how often",
         "usually go")
SUMMARY = ("tolkhis", "telkhis", "mlakhas", "molakhas", "lakhesle", "lakhisle", "lakhes", "lakhis", "summary",
           "summarize", "summarise", "sum up")
BROKE = ("aflaset", "2aflaset", "aflasna", "2aflasna", "tayaret", "tiro", "yekhtefe", "khtafa", "broke", "flew",
         "flying", "disappearing")
PHARMACY = ("pharmacie", "pharmacy", "pharmacies")
BRAND_WORDS = ("brand", "brands", "marka", "naw3", "nou3", "kind", "type")
CHEAPER_WORDS = ("arkhas", "arkhasle", "awfar", "awfarle", "arkhas shi", "cheaper", "cheapest", "better value")
BETTER_WORDS = ("ahsan", "a7san", "afdal", "afdalle", "better", "best")

# Lead-ins from the user's seeds (A, 2026-11-16): the group a version must contain, and how to write it.
LEAD_INS = {
    "became": (("sert", "soret", "seret", "sort", "serit", "sir", "2edmen", "edmen", "m2admin", "m2ademne", "mahwous",
                "mahwouse", "zboun", "zbounet", "obsessed", "addicted", "hooked", "regular"),
               ("a lead-in saying they have BECOME obsessed with, addicted to or a regular of it (sert mahwous / "
                "mahwouse bi, 3ende 2edmen aa, m2admin / m2ademne 3al, soret zboun / zbounet). Here sert / soret means "
                "'I have become', NOT 'so far'")),
    "feel": (("7eses", "heses", "7esa", "hesa", "hase", "hasis", "hases", "7asis", "7ases", "hasse", "7asse", "feel",
              "feels"),
             ("a lead-in with a feeling: 7eses / heses hale (m), 7esa / hase / hesa (f) ..., e.g. 'I feel like I live at "
              "the gas station' (7eses hale aayesh / 7esa hale aayshe bi X); 'hase el masari aam tekhtefe' has no hali")),
    "mom": (("emme", "mama", "mom", "mum", "mother"), "a lead-in quoting their mom (emme aletle ...)"),
    "trying": (("7awil", "hawil", "jareb", "khafif", "khafef", "2e2ta3", "o2taa", "o2ta3", "wa2ef", "trying",
                "cut down", "quit", "stop"),
               "a lead-in saying they are trying to cut down or quit (aam 7awil khafif, 3am jareb 2e2ta3, badi wa2ef)"),
    "save": (("wafir", "wafer", "waffer", "save", "saving"),
             ("a lead-in saying they want to save money (badi wafir heda el shaher). The question itself is answered "
              "from the receipts, so it is NOT advice and NOT UNSUPPORTED")),
    "know": (("a3ref", "2a3ref", "aarf", "aaref", "2a3rf", "know"),
             ("a lead-in 'I want to know' (badi a3ref / 7abe 2a3ref (f) / 7abeb 2a3ref (m) / habbe aarf), sometimes "
              "with a money idiom (wayn aam bi tiro mosriyete / el masare, wayn 3am yekhtefe ma3ashe)")),
}

SPELLINGS = (" In most Arabizi versions say 'I bought' as jebet or shtrit (jebto / jebta / jebton, shtrito / shtrita / "
             "shtriton), and use aal / aa as often as 3al / 3a.")


def load_batch4_catalogue() -> Catalogue:
    return load_catalogue(extension=(BATCH3_EXTENSION, BATCH4_EXTENSION))


def batch4_user(number: int, catalogue: Catalogue | None = None) -> UserData:
    catalogue = catalogue or load_batch4_catalogue()
    return UserData(make_user(catalogue, number, today=TODAYS[number]), catalogue)


# --- periods ---


def since_start_of_year(today: date) -> Period:
    p = periods.since_start_of_year(today)  # the user's "mn awalt el sene" too (2026-11-16)
    return replace(p, words=p.words + ("mn awalt el sene", "men awalt el sene", "hal sene", "hay el sene", "hay l sene"))


# The user's "ekher / e5er" forms (chunk-2 review, 2026-11-16), added for batch 4 only: batch 3's periods stay as they were.
EXTRA_WORDS = {"last_week": ("ekher jemaa", "ekher jem3a", "e5er jemaa", "e5er jem3a"), "last_month": ("e5er shaher",)}


def _with_extra(kind: str) -> Callable[[date], Period]:
    def period(today: date) -> Period:
        p = b3.COMMON[kind](today)
        words = p.words + tuple(w for w in b3.EXTRA_WORDS.get(kind, ()) + EXTRA_WORDS[kind] if w not in p.words)
        return replace(p, words=words)

    return period


NEW_PERIODS: dict[str, Callable[[date], Period]] = {
    "last_week": _with_extra("last_week"), "last_month": _with_extra("last_month"),
    "last_year": periods.last_year, "last_2_years": lambda today: periods.last_years(today, 2),
    "last_few_weeks": periods.last_few_weeks, "since_summer": periods.since_summer, "summer": periods.summer,
    "since_start_of_year": since_start_of_year,
}  # fmt: skip


def period_named(data: UserData, kind: str, rng: random.Random) -> Period:
    return NEW_PERIODS[kind](data.today) if kind in NEW_PERIODS else b3.period_named(data, kind, rng)


def _kind(kind: str) -> str | Callable[[date], Period]:
    """What batch 3's makers take: a name they know, or one of batch 4's period functions."""
    return NEW_PERIODS.get(kind, kind)


def _with(spec: Spec | None, note: str = "", *groups: tuple[str, ...], template: str | None = None,
          **labels) -> Spec | None:  # fmt: skip
    if spec is None:
        return None
    return Spec(template or spec.template, spec.kind, spec.description + note, spec.target,
                spec.mentions + tuple(g for g in groups if g), spec.reply_hint, spec.base, {**spec.labels, **labels})


# --- A. lead-ins ---


MAKERS: dict[str, Callable[..., Spec | None]] = {
    "visits": b3.visits, "times": b3.times_bought, "quantity": b3.quantity, "item_spend": b3.item_spend,
    "shop_total": b3.shop_total, "total": b3.total, "where": b3.where_money_went, "top_shop": b3.top_shop,
    "receipts": b3.receipts,
}  # fmt: skip


def lead_in(data: UserData, rng: random.Random, style: str, what: str, kind: str) -> Spec | None:
    words, how = LEAD_INS[style]
    spec = MAKERS[what](data, rng, _kind(kind))
    note = f" Every version starts with {how}, then asks the question. The lead-in does not change the answer."
    return _with(spec, note + SPELLINGS, words, lead_in=style)


# --- B. aday as a count, next to "bi aday" (price) and aday + a money word ---


def _countable(item) -> bool:
    return not item.weight_g and not item.litres and item.name not in NOT_PRICED  # the bills and phone recharge


def aday_set(data: UserData, rng: random.Random, kind: str) -> list[Spec]:
    """Four questions on the same item and period that differ only in what they measure (the user's rule,
    2026-11-16: aday is usually a count; "bi aday jebet el X" is the price; aday + dafa3et / sarafet is money; "aday
    akalet bi <restaurant>" is how many times they ate there)."""
    p = period_named(data, kind, rng)
    items = [n for n in b3._bought_items(data, p) if _countable(data.catalogue.item(n))]
    if not items:
        return []
    item = data.catalogue.item(rng.choice(items))
    words = t.item_words(item)
    where = t._where(t.item_is(item.name), p.sql)
    specs = [
        t._spec("T15", f"How many {item.name} the user bought, {p.description}. Asked with aday meaning HOW MANY "
                "(aday jebet / aday shtrit / aday aam jib el X), with NO money word." + SPELLINGS,
                f"SELECT SUM(quantity) AS quantity_bought FROM purchases{where}", p, words, AS_COUNT, BOUGHT,
                item=item.name, aday="count"),
        t._spec("T12", f"What the user paid for {item.name} (the price they got it for: average, lowest and highest), "
                f"{p.description}. Asked with 'bi aday' (bi aday jebet el X / bi aday aam jib el X)." + SPELLINGS,
                t._average(item, p, t.UNIT_PRICE, None), p, words, BI_ADAY, item=item.name, aday="price"),
        t._spec("T9", f"How much money the user spent on {item.name}, {p.description}. Asked with aday + a money word "
                "(aday dafa3et / sarafet aal X).", t.money("purchases", "line_total", t.item_is(item.name), p.sql),
                p, words, MONEY, item=item.name, aday="money"),
    ]  # fmt: skip
    dining = sorted({r.shop for r in data.receipts_in(p) if data.shop(r.shop).kind in DINING_KINDS})
    if dining:
        specs.append(_times_there(data, rng, p, rng.choice(dining)))
    return specs


def _times_there(data: UserData, rng: random.Random, p: Period, shop: str) -> Spec:
    """'aday akalet bi <restaurant>' counts visits; at a cafe the user names the drink ('aday shrebet ahwe bi X',
    2026-11-16), which counts the receipts with that drink there."""
    vendor = f"vendor = {t.quoted(shop)}"
    drinks = sorted({line.item for r, line in data.lines if r.shop == shop and t._within(r.day, p)})
    if data.shop(shop).kind == "cafe" and drinks:
        drink = rng.choice(drinks)
        target = f"SELECT COUNT(DISTINCT receipt_id) AS times FROM purchases{t._where(t.item_is(drink), vendor, p.sql)}"
        return t._spec("T14", f"How many times the user had {drink} at {shop}, {p.description}. Asked with aday + "
                       "shrebet / akalet + the drink + bi <shop> (aday shrebet ahwe bi X): bi here means AT, not a "
                       "price.", target, p, t.item_words(data.catalogue.item(drink)), t.shop_words(data.shop(shop)),
                       AS_COUNT, EAT_DRINK, shop=shop, drink=drink, aday="times")  # fmt: skip
    target = f"SELECT COUNT(DISTINCT receipt_id) AS visits FROM receipts{t._where(vendor, p.sql)}"
    return t._spec("T8", f"How many times the user ate at {shop}, {p.description}. Asked with aday + akalet bi <shop> "
                   "(aday akalet bi X): bi here means AT, not a price.", target, p, t.shop_words(data.shop(shop)),
                   AS_COUNT, EAT_DRINK, shop=shop, aday="times")  # fmt: skip


# --- C. other verbs, counting words and units ---


def _dining_item(item) -> bool:
    return item.category == "Dining" or item.name in ("coffee", "iced coffee", "energy drink", "argile")


def eaten_times(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    p = period_named(data, kind, rng)
    pool = [n for n in b3._bought_items(data, p) if _dining_item(data.catalogue.item(n))]
    if not pool:
        return None
    item = rng.choice(pool)
    target = f"SELECT COUNT(DISTINCT receipt_id) AS times FROM purchases{t._where(t.item_is(item), p.sql)}"
    return t._spec("T14", f"How many times the user ate or drank {item}, {p.description}. Asked with kam mara + "
                   "akalet / shrebet / seret ekle (soret ekel), or 3ed kam mara.", target, p,
                   t.item_words(data.catalogue.item(item)), EAT_DRINK, TIMES, item=item)  # fmt: skip


def went_times(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    return _with(b3.visits(data, rng, _kind(kind)), " Asked with kam mara / shu 3adad el marat + rehet / daharet / ro7t "
                 "(aa / 3a / aal the shop).", GO)  # fmt: skip


def _item_times(data: UserData, rng: random.Random, kind: str, item: str, how: str, verbs: tuple[str, ...]
                ) -> Spec | None:  # fmt: skip
    if item not in data.items:
        return None
    p = period_named(data, kind, rng)
    target = f"SELECT COUNT(DISTINCT receipt_id) AS times FROM purchases{t._where(t.item_is(item), p.sql)}"
    return t._spec("T14", f"How many times the user {how}, {p.description}.", target, p,
                   t.item_words(data.catalogue.item(item)), verbs, TIMES, item=item)  # fmt: skip


def fuel_times(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    return _item_times(data, rng, kind, "fuel", "filled up with fuel (kam mara 3abayt benzine)", FILL)


def haircut_times(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    return _item_times(data, rng, kind, "haircut", "had a haircut (kam mara 2asayt sha3re)", CUT)


def counted_receipts(data: UserData, rng: random.Random, kind: str, at_shop: bool = False) -> Spec | None:
    return _with(b3.receipts(data, rng, _kind(kind), at_shop), " Asked with a counting word: 3ed / 3edele kam fatoura, "
                 "3adad / aadad el fwatir, or kam fatoura 3ende.", COUNTING)  # fmt: skip


def units_bought(data: UserData, rng: random.Random, kind: str) -> Spec | None:
    p = period_named(data, kind, rng)
    pool = [n for n in b3._bought_items(data, p) if _countable(data.catalogue.item(n))
            and data.catalogue.item(n).sizes]  # fmt: skip
    if not pool:
        return None
    item = rng.choice(pool)
    target = f"SELECT SUM(quantity) AS quantity_bought FROM purchases{t._where(t.item_is(item), p.sql)}"
    return t._spec("T15", f"How many {item} the user bought, counted in its unit (kam 3elbit X, kam sandu2 X, how many "
                   f"packs), {p.description}." + SPELLINGS, target, p, t.item_words(data.catalogue.item(item)), UNITS,
                   item=item)  # fmt: skip


# --- D. new kinds: the last time, the dates of visits, how often ---


def _shops(data: UserData, period: Period | None = None) -> list[str]:
    found = {r.shop for r in data.receipts_in(period)} if period else set(data.shops)
    return sorted(s for s in found if data.shop(s).kind not in MONTHLY_KINDS)


def last_time(data: UserData, rng: random.Random, at_shop: bool) -> Spec | None:
    if at_shop:
        shops = _shops(data)
        shop = rng.choice(shops) if shops else None
        if shop is None:
            return None
        return Spec("B11", "sql", f"When was the last time the user went to {shop} (aymta / aymata ekher mara rehet "
                    "...).", f"SELECT MAX(receipt_date) AS last_time FROM receipts WHERE vendor = {t.quoted(shop)}",
                    (t.shop_words(data.shop(shop)), LAST_TIME), labels={"period": "none", "shop": shop})  # fmt: skip
    items = [n for n in data.items if n not in MONTHLY_BILLS]
    item = rng.choice(items) if items else None
    if item is None:
        return None
    return Spec("B11", "sql", f"When was the last time the user bought (or ate, drank, had) {item} (aymta / aymata "
                "ekher mara jebet / akalet / shrebet ...)." + SPELLINGS,
                f"SELECT MAX(receipt_date) AS last_time FROM purchases WHERE item_name = {t.quoted(item)}",
                (t.item_words(data.catalogue.item(item)), LAST_TIME), labels={"period": "none", "item": item})  # fmt: skip


def visit_dates(data: UserData, rng: random.Random, kind: str, pharmacy: bool = False) -> Spec | None:
    p = period_named(data, kind, rng)
    if pharmacy:
        shops = sorted(s for s in data.shops if data.shop(s).kind == "pharmacy")
        if not shops:
            return None
        vendor = f"vendor IN ({', '.join(t.quoted(s) for s in shops)})"
        words, what = PHARMACY, "a pharmacy (any of the user's pharmacies)"
    else:
        visited = _shops(data, p)
        if not visited:
            return None
        shop = rng.choice(visited)
        vendor, words, what = f"vendor = {t.quoted(shop)}", t.shop_words(data.shop(shop)), shop
    target = f"SELECT receipt_date, vendor FROM receipts{t._where(vendor, p.sql)} ORDER BY receipt_date"
    return t._spec("B12", f"On which dates the user went to {what}, {p.description} (aymta / aymata rehet ...).", target,
                   p, words, WHEN, pharmacy=pharmacy)  # fmt: skip


def how_often(data: UserData, rng: random.Random) -> Spec | None:
    months = b3.Period("last_3_complete_months", "receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL "
                       "'3 months' AND receipt_date < date_trunc('month', CURRENT_DATE)", None, None, "", ())
    shops = _shops(data)
    if not shops:
        return None
    shop = rng.choice(shops)
    target = (f"SELECT ROUND(COUNT(DISTINCT receipt_id) / 3.0, 1) AS visits_per_month FROM receipts"
              f"{t._where(f'vendor = {t.quoted(shop)}', months.sql)}")
    return Spec("B13", "sql", f"How often the user goes to {shop}, with NO period named (aday 3am ru7 aand X, kam mara "
                "3am ru7 aa X): visits per month over the last 3 complete months.", target,
                (t.shop_words(data.shop(shop)), OFTEN), labels={"period": "last_3_complete_months", "shop": shop})  # fmt: skip


# --- E. periods and summaries ---


def in_period(data: UserData, rng: random.Random, what: str, kind: str) -> Spec | None:
    return _with(MAKERS[what](data, rng, _kind(kind)), SPELLINGS)


def summary(data: UserData, rng: random.Random, kind: str, broke: bool = False) -> Spec | None:
    spec = b3.where_money_went(data, rng, _kind(kind))
    if broke:
        return _with(spec, " Said as a complaint about money disappearing (aflaset / 2aflasna 3al akid, ru7 shuf 3a shu "
                     "tayaret el masare; wayn 3am yekhtefe ma3ashe).", BROKE, template="B14")  # fmt: skip
    return _with(spec, " Asked as a summary: 3tine tolkhis / 3mele telkhis 3an ..., lakhesle / lakhisle ..., or (rarely, "
                 "formal) mlakhas.", SUMMARY, template="B14")  # fmt: skip


# --- F. REPLY and CLARIFY ---


REPLY_KINDS = (
    ("R1", "a greeting asking if the assistant is there (marhaba, kifak? enta hon?)",
     "Greet them back and say you are here to help with their receipts."),
    ("R1", "a short greeting alone (hi kifak, marhaba, salut, sabah el kheir, shu el wade3)",
     "Greet them back and say what you can help with."),
    ("R2", "thanks (ok merci ktir, ya3tik el 3afye)", "Say you're welcome."),
    ("R5", "a sign-off: that's all, they need nothing else, bye, talk later (khalas ma ba2 baddi shi, yalla bye)",
     "Say goodbye kindly."),
    ("R3", "what the assistant can do (shu fik tse3edne fi? shu bta3ref ta3mel?)",
     "Say it answers questions about their own receipts: totals, categories, shops, items, prices and comparisons."),
)  # fmt: skip


def greeting(data: UserData, rng: random.Random, index: int) -> Spec:
    template, about, hint = REPLY_KINDS[index % len(REPLY_KINDS)]
    return Spec(template, "reply", f"The user sends {about}. No question about receipts.", None, (),
                hint + " Never state amounts.", labels={"reply": index % len(REPLY_KINDS)})


def lost_receipt(data: UserData, rng: random.Random) -> Spec | None:
    item = rng.choice(data.items) if data.items else None
    if item is None:
        return None
    return Spec("C7", "clarify", f"The user bought {item} but cannot find its receipt and asks the assistant to find it, "
                "maybe under another name (shtrit X bas ma aam le2e el fatoura, fik tle2ele yeha?).", None,
                (t.item_words(data.catalogue.item(item)),), "Ask when and where they bought it, or what else it may "
                "be called on the receipt.", labels={"item": item})  # fmt: skip


def vague_place(data: UserData, rng: random.Random) -> Spec:
    about, what = rng.choice([("shop", "'that shop next to my work' (el mahal yali had / 7ad el sheghel)"),
                              ("item", ("'the thing I bought last week' (el shaghle yali shtarayta ekher jemaa) "
                                        "with nothing named"))])  # fmt: skip
    return Spec("C3", "clarify", f"A question about {what}, so it is not clear which shop or item they mean.", None, (),
                f"Ask which {about} they mean.", labels={"about": about})


def beginning_of_month(data: UserData, rng: random.Random) -> Spec:
    what = rng.choice(["how many times they went somewhere", "how much they spent", "how much they paid for an item"])
    return Spec("C4", "clarify", f"The user asks {what} 'bi awal el shaher' (at the beginning of the month), which is "
                "not a clear period.", None, (("bi awal el shaher", "bi awalt el shaher", "beginning of the month",
                                              "start of the month"),),
                "Ask exactly which period they mean.", labels={"period": "bi awal el shaher"})  # fmt: skip


def unknown_item(data: UserData, rng: random.Random) -> Spec | None:
    return _with(t.c1_unknown_item(data, rng), " Asked as a normal question; the answer is to ask back, NOT to refuse.")


def unknown_shop(data: UserData, rng: random.Random) -> Spec | None:
    return _with(t.c2_unknown_shop(data, rng), " Often a visit count (adde rehet aa X); ask back, NOT refuse.")


# --- G. brands (approved 2026-11-16) ---


def _brands(data: UserData, item: str) -> dict[str | None, set[str]]:
    found: dict[str | None, set[str]] = {}
    for _, line in data.lines:
        if line.item == item and line.brand:
            found.setdefault(line.size_unit, set()).add(line.brand)
    return found


def cheapest_brand(data: UserData, rng: random.Random) -> Spec | None:
    """'aya brand / aya naw3 X arkhasle?': every brand the item was bought in, by the same per-size rules as the
    cheapest shop, cheapest first; lines with no brand left out."""
    options = [(item, unit) for item in data.items if item not in NOT_PRICED
               for unit, brands in _brands(data, item).items() if len(brands) >= 2]  # fmt: skip
    if not options:
        return None
    item, unit = rng.choice(sorted(options, key=str))
    price, column, condition, wording = b3._basis(unit)
    target = (f"SELECT brand, currency, COUNT(*) AS purchase_count, ROUND(AVG({price}), 2) AS {column} FROM purchases"
              f"{t._where(t.item_is(item), condition, 'brand IS NOT NULL')} GROUP BY brand, currency "
              f"ORDER BY {column}, brand")  # fmt: skip
    return Spec("B15", "sql", f"Which brand (or kind) of {item} is cheaper for the user, comparing every brand they "
                f"bought ({wording}); asked as aya brand / aya naw3 {item} arkhasle / awfarle. No brand is named."
                + SPELLINGS, target, (t.item_words(data.catalogue.item(item)), BRAND_WORDS, CHEAPER_WORDS),
                labels={"period": "none", "item": item, "compared": wording})  # fmt: skip


def better_brand(data: UserData, rng: random.Random) -> Spec | None:
    items = sorted(i for i in data.items if any(_brands(data, i).values()))
    if not items:
        return None
    item = rng.choice(items)
    return Spec("C8", "clarify", f"Which brand or kind of {item} is BETTER (aya brand {item} ahsan / afdal): receipts "
                "show prices, not quality.", None, (t.item_words(data.catalogue.item(item)), BRAND_WORDS,
                                                   BETTER_WORDS),
                "Say you cannot tell which is better, but can check which is cheaper.", labels={"item": item})  # fmt: skip


# --- H. more CLARIFY / UNSUPPORTED, for the mix's 15% (approved 2026-11-16) ---


ADVICE = (
    ("save_what_to_do", "sends a lead-in saying they want to save (badi wafir) and then asks what they SHOULD do (shu lezem "
     "a3mel / shu ra2yak). Advice, so UNSUPPORTED, unlike 'badi wafir, aya ma7al sarafet fi aktar shi' which is answered"),
    ("save_what_to_stop", "sends a lead-in saying they want to save, then asks what they should stop buying (aya shi lezem "
     "wa2ef eshteri / shu ra2yak lezem wa2ef)"),
    ("should_stop_item", "sends a lead-in saying they are trying to cut down on something (coffee, cigarettes, delivery), then "
     "asks whether they SHOULD stop (lezem wa2ef?)"),
    ("where_to_shop", "asks where they should shop from now on to pay less (wen lezem ru7 / shu ra2yak)"),
    ("next_month", "asks how much they WILL spend next month (aday ra7 esrof el shaher el jeye), a prediction"),
    ("bank_balance", "asks how much money is left in their bank account (ade be2e ma3e bl bank)"),
    ("someone_else", "asks how much someone else spent (my brother, my husband, my friend)"),
    ("how_to_save", "sends a lead-in about money disappearing (wayn 3am yekhtefe ma3ashe), then asks HOW to save (kif fiye "
     "wafir)"),
)  # fmt: skip


def advice(data: UserData, rng: random.Random, index: int) -> Spec:
    about, what = ADVICE[index % len(ADVICE)]
    return Spec("U6", "unsupported", f"The user {what}. The receipts cannot answer it.", "UNSUPPORTED",
                labels={"about": about})


def never_bought_count(data: UserData, rng: random.Random) -> Spec | None:
    spec = t.c1_unknown_item(data, rng)
    return _with(spec, " Asked as a count (kam mara jebet X / aday jebet X), not as spending.", asked_as="count")


def never_visited_count(data: UserData, rng: random.Random) -> Spec | None:
    spec = t.c2_unknown_shop(data, rng)
    return _with(spec, " Asked as a visit count (kam mara rehet aa X / aday rehet 3a X), not as spending.",
                 asked_as="count")


# --- the plan ---


@dataclass(frozen=True)
class Want:
    """How many specs of one kind to plan, spread over the users; a maker may return a list (a contrast set)."""

    maker: Callable[..., Spec | list[Spec] | None]
    count: int
    args: tuple = ()


WANTS = (
    # A. lead-ins (30)
    Want(lead_in, 2, ("became", "visits", "this_month")), Want(lead_in, 2, ("became", "times", "this_month")),
    Want(lead_in, 2, ("became", "visits", "last_month")),
    Want(lead_in, 2, ("feel", "item_spend", "this_month")), Want(lead_in, 2, ("feel", "shop_total", "this_week")),
    Want(lead_in, 1, ("feel", "total", "last_week")),
    Want(lead_in, 2, ("mom", "visits", "this_month")), Want(lead_in, 2, ("mom", "item_spend", "last_month")),
    Want(lead_in, 2, ("trying", "times", "last_week")), Want(lead_in, 2, ("trying", "item_spend", "this_month")),
    Want(lead_in, 2, ("trying", "quantity", "this_week")),
    Want(lead_in, 2, ("save", "where", "this_month")), Want(lead_in, 2, ("save", "top_shop", "this_month")),
    Want(lead_in, 1, ("save", "item_spend", "last_month")),
    Want(lead_in, 2, ("know", "where", "last_month")), Want(lead_in, 2, ("know", "shop_total", "this_month")),
    # B. aday sets (10 sets, up to 4 each)
    Want(aday_set, 3, ("this_month",)), Want(aday_set, 3, ("last_month",)), Want(aday_set, 2, ("this_week",)),
    Want(aday_set, 1, ("last_week",)), Want(aday_set, 1, ("last_year",)),
    # C. other verbs, counting words, units (20)
    Want(eaten_times, 5, ("this_month",)), Want(went_times, 3, ("last_month",)), Want(fuel_times, 2, ("this_week",)),
    Want(haircut_times, 2, ("since_start_of_year",)), Want(counted_receipts, 2, ("last_week",)),
    Want(counted_receipts, 2, ("this_month", True)), Want(units_bought, 4, ("this_week",)),
    # D. new kinds (23)
    Want(last_time, 6, (False,)), Want(last_time, 4, (True,)), Want(visit_dates, 2, ("since_start_of_year",)),
    Want(visit_dates, 1, ("this_month",)), Want(visit_dates, 2, ("since_start_of_year", True)), Want(how_often, 8),
    # E. periods (20) and summaries (5)
    Want(in_period, 3, ("total", "last_year")), Want(in_period, 2, ("item_spend", "last_year")),
    Want(in_period, 3, ("visits", "last_2_years")), Want(in_period, 2, ("shop_total", "since_summer")),
    Want(in_period, 2, ("times", "summer")), Want(in_period, 2, ("total", "last_few_weeks")),
    Want(in_period, 1, ("top_shop", "last_few_weeks")), Want(in_period, 2, ("visits", "since_start_of_year")),
    Want(in_period, 1, ("item_spend", "since_summer")), Want(in_period, 2, ("receipts", "last_year")),
    Want(summary, 1, ("last_2_years",)), Want(summary, 1, ("last_year",)), Want(summary, 1, ("this_month",)),
    Want(summary, 1, ("last_month",)), Want(summary, 1, ("last_few_weeks", True)),
    # F. REPLY (7) and CLARIFY (11)
    Want(greeting, 7), Want(unknown_item, 3), Want(unknown_shop, 2), Want(lost_receipt, 2), Want(vague_place, 2),
    Want(beginning_of_month, 2),
    # Added last (2026-11-16), so no other spec moves: "aflaset 3al akid hal jemaa" (broke, this week).
    Want(summary, 1, ("this_week", True)),
    # Added last (2026-11-16): which brand is cheaper, and which is better (CLARIFY).
    Want(cheapest_brand, 6), Want(better_brand, 3),
    # Added last (2026-11-16): the mix's CLARIFY + UNSUPPORTED share had fallen to 14.4% (approved minimum 15%).
    Want(advice, 8), Want(never_bought_count, 2), Want(never_visited_count, 2),
)


def plan(numbers: tuple[int, ...], one_each: bool = False, catalogue: Catalogue | None = None
         ) -> dict[int, list[Spec]]:  # fmt: skip
    """Every wanted spec (or contrast set), given to the users in turn (a user that cannot make one passes it on). The
    validation users get one of each kind of want (`one_each`). Deterministic for the same users."""
    catalogue = catalogue or load_batch4_catalogue()
    users = {n: batch4_user(n, catalogue) for n in numbers}
    specs: dict[int, list[Spec]] = {n: [] for n in numbers}
    seen: set[tuple] = set()
    done: set[tuple] = set()
    turn = 0
    for want_index, want in enumerate(WANTS):
        kind = (want.maker, want.args[:1]) if want.maker is lead_in else (want.maker,)
        if one_each and kind in done:
            continue
        done.add(kind)
        for copy in range(1 if one_each else want.count):
            for attempt in range(len(numbers) * 3):
                number = numbers[(turn + attempt) % len(numbers)]
                rng = random.Random(f"{SEED_PREFIX}/{number}/{want_index}/{copy}/{attempt}")
                args = (copy,) if want.maker in (greeting, advice) else want.args
                made = want.maker(users[number], rng, *args)
                group = [s for s in (made if isinstance(made, list) else [made]) if s is not None]
                keys = [(number, s.template, s.target, s.description) for s in group]
                if group and not any(k in seen for k in keys):
                    seen.update(keys)
                    specs[number].extend(group)
                    break
            turn += 1
    return specs
