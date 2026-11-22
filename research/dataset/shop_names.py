"""Random shop names in the training mix ("Light", decided with Christina on 2026-11-22; PROGRESS.md "name resolution").

Every training query named one of the same 64 catalogue shops, and 8 shops only ever got "no receipts", so the
model could learn names instead of reading the user's list. When the mix is built (the stored batches stay as
reviewed), this module:
- swaps, in about 30% of the examples whose replies name a shop, each such shop for a made-up Lebanese-style one of
  the same kind (a printed kind word + a family name: Supermarché Saadeh, Boulangerie Nassif, Snack Abou Nader), in
  the user's list, the questions (any spelling the catalogue has for it), the SQL and the replies, earlier turns
  included; the 8 "no receipts only" shops are always swapped; a made-up name is the answer at most 3 times;
- pads the user's shop list with made-up names to 20-100 (the app's cap is 100), at random places, never of a kind
  the example mentions and never a pharmacy (the prompt picks pharmacies by name), so no reply becomes wrong;
- keeps 15% of the family and first names out of training (HELD_OUT), for fine-tune 5's test.
Bills, subscriptions, taxis, delivery apps, cinemas, tobacco and department stores keep their real names (no local
ones exist); items and the answer-step examples are not touched. Printed names only: no spoken forms (her choice:
"Light"; the gap is a documented limitation).
"""

import json
import random
import re
from collections import Counter

from app.domain.assistant.prompt import Exchange, UserNames, build_prompt

from research.dataset import build
from research.dataset import templates as t
from research.dataset.rerender import UnreadablePrompt, read_prompt
from research.dataset.users import gender_of

SEED = "fyp-dataset/batch5-shop-names"
SWAP_SHARE, MOST_ANSWERS, PAD_LEAST, PAD_MOST = 0.3, 3, 20, 100
ASK_BACK_ONLY = ("McDonald's", "Sushi Co", "Maliks", "Dunkin", "Grand Cinemas", "Virgin Megastore", "Feel22",
                 "IQOS Boutique")  # fmt: skip
SURNAMES = (
    "Saadeh Nassif Rizkallah Haddad Gemayel Chamoun Frangieh Karam Sfeir Tannous Daher Hajj Azar Moussa Issa Yammine "
    "Bitar Abboud Nakhle Ghanem Salameh Tabet Matar Mansour Nehme Harb Zein Fakhoury Najjar Sabbagh Hayek Chidiac "
    "Maalouf Assaf Rahme Daou Hobeika Kanaan Ghosn Akl Feghali Chahine Saliba Wehbe Zogheib Sleiman Merhi Itani "
    "Hamadeh Moukarzel Shehadeh Jaber Haidar Fares Atallah Kahwaji Barakat Mouawad Choueiri Tohme Raad Awad Khalaf "
    "Hachem Sarkis Bechara Maroun Najem Semaan Jabbour Khattar Rached Kfoury Ayoub Boustany Doumit Eid Hatem Mrad "
    "Obeid Saab Saber Tawk Younan Zahr Fayad Chedid Rahal Abi-Nader Abi-Khalil Abou-Jaoude Bou-Saab Nasr Sakr Helou "
    "Hosni Ghorayeb Mikati Daccache Lteif Massoud Abdallah Aziz Ibrahim Dib Gebran Habib Najm Rizk-Allah Wakim").split()  # fmt: skip
FIRST_NAMES = ("Nader Fadi Rami Samir Elie Georges Joseph Michel Ali Hassan Khaled Walid Ziad Karim Charbel Fouad "
               "Marwan Nabil Salim Wadih Youssef Imad Samer Hadi Bassam Raymond Toufic Jamil Sami Ghassan").split()  # fmt: skip
# Kind words as receipts print them: "X {name}" or "{name} X" (a leading "+").
PRINTED = {
    "supermarket": ("Supermarché", "Supermarket", "Market"), "minimarket": ("Mini Market", "Épicerie", "Alimentation"),
    "bakery": ("Boulangerie", "Furn", "Pâtisserie"), "pharmacy": ("Pharmacie",), "butcher": ("Boucherie",),
    "cafe": ("Café", "+Coffee"), "restaurant": ("Restaurant", "Chez"), "fast_food": ("Snack", "Shawarma"),
    "sweets": ("Pâtisserie", "Halawiyat"), "clothes": ("Boutique", "+Fashion"), "electronics": ("+Electronics",),
    "bookstore": ("Librairie",), "beauty": ("Salon", "+Beauty"), "home": ("+Home",), "nuts": ("Torréfaction",),
    "toys": ("+Toys",), "pets": ("+Pet Shop",), "sports": ("+Sports",), "gym": ("+Gym",), "fuel": ("Station",),
    "car_wash": ("+Car Wash",), "cinema": ("Cinéma",), "tobacco": ("Tabac",),
}  # fmt: skip
# Shop names that are also words ("total spent", "happy"): matched only as written, with the capital.
WORD_NAMES = {"Total", "Happy", "Stories", "Coop", "Coral", "Barista", "Foodies", "Hibou"}
PARTICLES = {"Bou", "Abi", "Abou"}  # parts of family names, not names themselves
WITH_FIRST_NAME = {"minimarket", "fast_food", "restaurant", "butcher", "sweets", "cafe"}  # "Snack Abou Nader"


def _catalogue_shops() -> dict[str, dict]:
    shops = {}
    for name in ("catalogue.json", "catalogue_batch3.json", "catalogue_batch4.json"):
        for shop in json.loads((build.DATA_DIR / name).read_text(encoding="utf-8"))["shops"]:
            shops[shop["name"]] = shop
    return shops


SHOPS = _catalogue_shops()


def _held_out() -> tuple[set[str], set[str]]:
    rng = random.Random(f"{SEED}/held-out")
    surnames, firsts = sorted(SURNAMES), sorted(FIRST_NAMES)
    rng.shuffle(surnames)
    rng.shuffle(firsts)
    return set(surnames[: len(surnames) * 15 // 100]), set(firsts[: len(firsts) * 15 // 100])


HELD_OUT = _held_out()


def _catalogue_words() -> set[str]:
    return {w.lower() for name in SHOPS for w in re.findall(r"[A-Za-z]+", name)}


def pool(kind: str, held_out: bool = False) -> list[str]:
    """Every made-up name of a kind: the training names, or (held_out) only the 15% kept for testing."""
    surnames, firsts = HELD_OUT
    taken = _catalogue_words()
    held_words = {w for name in surnames | firsts for w in name.split("-")} - PARTICLES  # "Bou-Saab" holds out "Saab"
    if held_out:
        keep = lambda name: name in surnames | firsts  # noqa: E731
    else:
        keep = lambda name: not set(name.split("-")) & held_words  # noqa: E731
    names = [s.replace("-", " ") for s in SURNAMES if keep(s) and s.lower() not in taken]
    if kind in WITH_FIRST_NAME:
        names += [f"Abou {f}" for f in FIRST_NAMES if keep(f) and f.lower() not in taken]
    found = [f"{name} {word[1:]}" if word.startswith("+") else f"{word} {name}" for word in PRINTED[kind] for name in names]
    return [n for n in found if n not in SHOPS]


POOLS = {kind: pool(kind) for kind in PRINTED}


def _spellings(shop: str) -> list[str]:
    entry = SHOPS[shop]
    return sorted({shop, *entry.get("nicknames", ()), *entry.get("suggested", ())}, key=len, reverse=True)


def _flags(spelling: str) -> int:
    return 0 if spelling in WORD_NAMES else re.IGNORECASE


def _named(text: str, spelling: str) -> bool:
    return re.search(rf"(?<![\w']){re.escape(spelling)}(?![\w'])", text, _flags(spelling)) is not None


def _replace(text: str, spelling: str, new: str) -> str:
    return re.sub(rf"(?<![\w']){re.escape(spelling)}(?![\w'])", lambda _: new, text, flags=_flags(spelling))


def referenced(replies: list[str]) -> list[str]:
    """The catalogue shops the gold replies name: quoted in SQL that filters a vendor, or named in a CLARIFY / REPLY."""
    found = []
    for shop in SHOPS:
        quoted = t.quoted(shop)
        for reply in replies:
            if ("vendor" in reply and quoted in reply) or (reply.startswith(("CLARIFY:", "REPLY:", "UNSUPPORTED:"))
                                                            and _named(reply, shop)):  # fmt: skip
                found.append(shop)
                break
    return found


class Swapper:
    """Keeps count of how often a made-up name has been the answer, across the whole mix (one per split)."""

    def __init__(self, split: str):
        self.split = split
        self.answers = Counter()

    def _new_name(self, kind: str, rng: random.Random, avoid: set[str]) -> str:
        choices = [n for n in POOLS[kind] if self.answers[n] < MOST_ANSWERS and n not in avoid]
        name = rng.choice(choices)
        self.answers[name] += 1
        return name

    def swapped(self, row: dict, index: int) -> dict:
        if row["labels"]["kind"] == "answer":
            return row
        try:
            parts = read_prompt(row["messages"][0]["content"])
        except UnreadablePrompt:
            return row
        rng = random.Random(f"{SEED}/{self.split}/{index}")
        reply = row["messages"][1]["content"]
        replies = [reply, *(e.reply for e in parts.history)]
        questions = [parts.question, *(e.question for e in parts.history)]
        named = [s for s in referenced(replies) if SHOPS[s]["kind"] in PRINTED]
        swap = [s for s in named if s in ASK_BACK_ONLY]
        if rng.random() < SWAP_SHARE:
            swap = named
        vendors = list(parts.names.vendors)
        mapping = {}
        for shop in swap:
            mapping[shop] = self._new_name(SHOPS[shop]["kind"], rng, set(vendors) | set(mapping.values()))

        def in_question(text: str) -> str:
            for shop, new in mapping.items():
                for spelling in _spellings(shop):
                    text = _replace(text, spelling, new)
            return text

        def in_reply(text: str) -> str:
            for shop, new in mapping.items():
                text = text.replace(t.quoted(shop), t.quoted(new))
                if text.startswith(("CLARIFY:", "REPLY:", "UNSUPPORTED:")):
                    text = _replace(text, shop, new)
            return text

        vendors = [mapping.get(v, v) for v in vendors]
        mentioned = {SHOPS[s]["kind"] for s in SHOPS if any(_named(x, s) for x in questions + replies)}
        mentioned |= {SHOPS[s]["kind"] for s in mapping}
        target = rng.randint(PAD_LEAST, PAD_MOST)
        kinds = [k for k in PRINTED if k not in mentioned and k != "pharmacy"]
        padded = 0
        while len(vendors) < target and kinds:
            name = rng.choice(POOLS[rng.choice(kinds)])
            if name not in vendors:
                vendors.insert(rng.randint(0, len(vendors)), name)
                padded += 1
        history = tuple(Exchange(in_question(e.question), in_reply(e.reply)) for e in parts.history)
        names = UserNames(items=parts.names.items, vendors=vendors, categories=parts.names.categories)
        prompt = build_prompt(in_question(parts.question), names, parts.today, history, gender=gender_of(row["labels"]["user"]))
        new = {**row, "messages": [{**row["messages"][0], "content": prompt}, {**row["messages"][1], "content": in_reply(reply)}],
               "labels": {**row["labels"], "shop_swap": mapping, "padded": padded}}  # fmt: skip
        return new
