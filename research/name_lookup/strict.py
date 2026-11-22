"""The stricter shop-name lookup (her choice (b), 2026-11-22; PROGRESS.md "name lookup test").

    python -m research.name_lookup.strict             # the development set (the first test, now used to tune)
    python -m research.name_lookup.strict --fresh     # the real test: lines written by a new agent, unseen

The first lookup (lookup.py) failed its test: a fuzzy match was taken as the shop, but Arabic names that differ by a
vowel or one letter (Hassan / Hussein, Haddad / Hadid) look the same to any spelling matcher. So this one only ANSWERS
on an exact match after folding the spelling, ASKS ("did you mean X?" / "X aw Y?") on anything fuzzy, and says NONE
("no receipts") otherwise. Python's standard library only.

- Folding: lower case, accents dropped, Arabizi digits (7 -> h, 5 -> kh, 3 and 2 dropped), ch -> sh, ou / oo -> u,
  ee / ei -> i, y -> i, q / c -> k, ph -> f, double letters single, a final h after a vowel dropped.
- Little words (el, 3and, mn, bi, ...) and kind words (furn, boulangerie, saydaliyet, pharmacie, épicerie, ...) are
  set aside; what is left of a shop's name is its distinctive words. Name prefixes (abou, abi, em, ...) never match
  alone.
- Common words: words found in 10 or more training questions that name no shop ("3edele", "total", "hal") never
  match a shop alone (the first test's "3edele" -> EDL).
- ANSWER: every distinctive word of one shop is in the question, or one of its words that no other listed shop has.
  Two such shops: ASK which. Otherwise any distinctive word within difflib ratio 0.8 of a question word (4+ letters):
  ASK "did you mean", the 2 best. Otherwise NONE.
"""

import argparse
import difflib
import json
import random
import re
from collections import Counter

from research.name_lookup.lookup import KIND_OF as FIRST_KINDS
from research.name_lookup.lookup import LITTLE as FIRST_LITTLE
from research.name_lookup.lookup import ROOT, TEST_DIR, _lines, _plain, catalogue_names, consonants, fold

MORE_KINDS = {
    "grocery": "supermarche epicerie alimentation khodarje khodarji fruits legumes primeur",
    "bakery": "manakish man2oushe boulangerie",
    "shawarma": "shawarma",
    "falafel": "falafel",
    "pizza": "pizza pizzeria",
    "grill": "grill",
    "food": "brasserie traiteur",
    "hair": "barber barbershop beaute beauty 7ala2 7alla2",
    "hardware": "quincaillerie hardware",
    "shoes": "chaussures shoes",
    "tyres": "pneus pneu tyres",
    "sweets": "glace glacier halawiyet 7alawiyet chocolatier",
    "nuts": "torrefaction mkassarat roastery",
    "florist": "fleurs fleuriste florist",
    "optician": "optique optic",
    "fuel": "station",
    "phones": "mobile cellular",
    "stationery": "papeterie",
    # added after the second test (round 3, 2026-11-22)
    "phones2": "telecom",
    "beauty": "lounge",
    "sandwiches": "sandwiches sandwich",
    "tools": "tools",
    "garage": "service garage",
    "shoe repair": "cordonnerie skafe",
    "garden": "jardinerie mashtal nabatet",
    "dry cleaning": "teinturerie",
    "fish": "pecherie",
    "cafe2": "kahwet kahwe ahwet",
    "manakish": "man2oushet manouchet manakeesh",
    "clothes2": "fashion",
    "juice": "cocktail",
    "fuel2": "m7atit m7atet m7atta",
}
KIND_OF = {**FIRST_KINDS, **{w: k for k, ws in MORE_KINDS.items() for w in ws.split()}}
LITTLE = FIRST_LITTLE | {"et", "shop", "store", "s", "sons", "for", "men", "co"}
PREFIXES = {fold(w) for w in "abou abu abi bou em oum um ibn".split()}
SIMILAR, FUZZY_LEAST, COMMON_LEAST = 0.85, 5, 10
GENERIC_FOOD = "food"  # snack, restaurant, mat3am: fits any kind of food shop
FOOD = {"food", "shawarma", "falafel", "pizza", "grill"}
SEED = "fyp-name-lookup/no-shop"


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _plain(text).replace("'s ", " ").replace("'", ""))


def distinctive(name: str) -> list[str]:
    return [fold(w) for w in _words(name) if w not in LITTLE and w not in KIND_OF]


def no_shop_questions() -> list[str]:
    """Arabizi / mixed training questions whose query names no shop, one per question."""
    seen = []
    for line in (ROOT / "research" / "dataset" / "data" / "mix" / "train.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["labels"]["language"] == "english" or row["labels"]["kind"] != "sql" or "vendor" in row["messages"][1]["content"]:
            continue
        q = re.findall(r"^Question: (.*)$", row["messages"][0]["content"], re.M)[-1]
        if q not in seen:
            seen.append(q)
    return seen


def split_no_shop() -> tuple[set[str], list[str]]:
    """The common words (from all but 200 no-shop questions) and the 200 kept to test false asks."""
    questions = no_shop_questions()
    random.Random(SEED).shuffle(questions)
    held, rest = questions[:200], questions[200:]
    counts = Counter(w for q in rest for w in {fold(x) for x in _words(q)})
    return {w for w, n in counts.items() if n >= COMMON_LEAST}, held


def _kinds(text: str) -> set[str]:
    return {KIND_OF[w] for w in _words(text) if w in KIND_OF}


def _clash(asked: set[str], shop: set[str]) -> bool:
    """The question names a kind of shop that is not this shop's (a snack fits any food shop)."""
    if not asked or not shop or asked & shop:
        return False
    return not ((asked | shop) <= FOOD and GENERIC_FOOD in asked | shop)


def _other_name_after(word: str, words: list[str], name_words: list[str], common: set[str]) -> bool:
    """A name word in the question right after the matched one that this shop does not have ("layali beirut")."""
    at = words.index(word)
    after = words[at + 1] if at + 1 < len(words) else None
    return bool(after) and after not in common and after not in name_words and len(after) >= 3


def decide(question: str, names: list[str], common: set[str]) -> tuple[str, list[str]]:
    words = [fold(w) for w in _words(question) if w not in LITTLE and w not in KIND_OF]
    said, asked = set(words), _kinds(question)
    owners = Counter(w for n in names for w in set(distinctive(n)))
    exact = []
    for name in names:
        mine = [w for w in distinctive(name) if w not in PREFIXES]
        if not mine:
            continue
        # a kind the question names but the shop's kind is unknown: not sure either (round 3)
        unsure = _clash(asked, _kinds(name)) or bool(asked and not _kinds(name))
        joined = "".join(distinctive(name))
        if (all(w in said for w in distinctive(name)) and not all(w in common for w in mine)) or (
                len(distinctive(name)) > 1 and len(joined) >= 5 and joined in said):  # names run together
            exact.append((2, name, unsure))
        else:
            keys = [w for w in mine if w in said and owners[w] == 1 and w not in common and len(w) >= 3]
            if keys:
                exact.append((1, name, unsure or any(_other_name_after(k, words, mine, common) for k in keys)))
    if exact:
        best = max(rank for rank, _, _ in exact)
        top = [(n, unsure) for rank, n, unsure in exact if rank == best]
        sure = len(top) == 1 and not top[0][1]
        return ("ANSWER" if sure else "ASK"), [n for n, _ in top]
    fuzzy = []
    for name in names:
        mine = [w for w in distinctive(name) if w not in PREFIXES and len(w) >= FUZZY_LEAST]
        score = max((difflib.SequenceMatcher(None, a, b).ratio() for a in words if len(a) >= FUZZY_LEAST and a not in common
                     for b in mine), default=0.0)  # fmt: skip
        # vowels vary in Arabizi (khalid / Khaled): the same consonants are a candidate too (it only asks; round 3)
        if any(len(consonants(a)) >= 3 and a not in common and consonants(a) == consonants(b)
               for a in words for b in mine + [w for w in distinctive(name) if w not in PREFIXES]):
            score = max(score, SIMILAR)
        if score >= SIMILAR:
            fuzzy.append((score, name))
    if fuzzy:
        return "ASK", [n for _, n in sorted(fuzzy, reverse=True)[:2]]
    return "NONE", []


def run(path) -> dict:
    parts = _lines(path)
    names = sorted({n for _, n in parts["1"]} | set(catalogue_names()))
    common, held = split_no_shop()
    one = [(q, n, *decide(q, names, common)) for q, n in parts["1"]]
    two = [(q, n, *decide(q, names, common)) for q, n in parts["2"]]
    none = [(q, *decide(q, names, common)) for q in held]
    return {
        "names": len(names),
        "part 1": len(one),
        "part 1 success": sum(1 for _, n, act, shops in one if act in ("ANSWER", "ASK") and n in shops),
        "part 1 wrong answered": [(q, n, s) for q, n, act, s in one if act == "ANSWER" and n not in s],
        "part 1 answered directly": sum(1 for _, n, act, shops in one if act == "ANSWER" and shops == [n]),
        "part 2": len(two),
        "part 2 wrong answered": [(q, n, s) for q, n, act, s in two if act == "ANSWER"],
        "no-shop asked": [(q, act, s) for q, act, s in none if act != "NONE"],
        "missed": [(q, n, act, s) for q, n, act, s in one if n not in s],
        "asked": [(q, n, s) for q, n, act, s in one if act == "ASK" and n in s],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--third", action="store_true", help="the last round's unseen set (round 3)")
    parser.add_argument("--details", action="store_true", help="also print the lines (not before the first fresh run)")
    args = parser.parse_args(argv)
    path = TEST_DIR / ("third_questions.md" if args.third else "fresh_questions.md" if args.fresh else "agent_questions.md")
    r = run(path)
    p1 = r["part 1 success"] / r["part 1"]
    direct = r["part 1 answered directly"] / r["part 1"]
    asks = len(r["no-shop asked"]) / 200
    print(f"{path.name}: {r['names']} names")
    print(f"part 1: success {r['part 1 success']}/{r['part 1']} = {p1:.0%} (pass >= 90%); wrong shop answered "
          f"{len(r['part 1 wrong answered'])} (pass <= 1); answered directly {direct:.0%} (pass >= 60%)")
    print(f"part 2: wrong shop answered {len(r['part 2 wrong answered'])}/{r['part 2']} (pass <= 2)")
    print(f"no-shop questions: asked or answered a shop {len(r['no-shop asked'])}/200 = {asks:.0%} (pass <= 5%)")
    ok = p1 >= 0.9 and len(r["part 1 wrong answered"]) <= 1 and direct >= 0.6 and len(r["part 2 wrong answered"]) <= 2 \
        and asks <= 0.05  # fmt: skip
    print("PASS" if ok else "FAIL")
    if args.details:
        for key in ("missed", "part 1 wrong answered", "part 2 wrong answered", "no-shop asked", "asked"):
            print(f"-- {key}:")
            for row in r[key]:
                print("  ", row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
