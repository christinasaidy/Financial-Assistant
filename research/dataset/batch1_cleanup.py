"""Batch 1 cleanup: fixed by rule, from the audit of every batch-1 Arabizi/mixed question (2026-11-21; raw/batch5/
batch1_audit/, her rulings in the grammar notes). Each rule is a search-and-replace she approves from before/after
samples; a question it changes is replaced as a whole in batch 1's raw replies, then batch 1 is replayed.

Rules (applied in this order, each to the question and to a follow-up's earlier question):
- sarfet: "sarfet" (I spent) -> "sarafet" (her ruling: sarafet = I spent).
- li_ablo: "el marra li ablo" / "el time li ablo" -> "el marra li abla" / "el marra el abla" (marra is feminine).
- sa7abit: "sa7abit menne (aktar masari)" -> "sarafet aalayon aktar shi" / "kalafoune aktar shi" / "kalafuni aktar shi".
- jaybte: "adde ra7 / akhad men jaybte" -> "aday sarafet".
- kam_money: "kam" + a money verb or total -> "aday" (kam only counts; "kam dollar" stays).
- rejected_word: motawassit -> moyenne; li fetit -> li mar2it; baskawit -> baskot.
- dual: "2 / tneen shhour|shaher" -> "shahrain"; "2 / tneen jem3a|jemaa|osbou3", "osbou3en" -> "jem3ten".
- period (before articles): see below.
- articles: "bi el" -> "bel", "3a el" / "3al el" -> "3al", "l el" -> "lal", "bi bel miyye" -> "bel miyye", "el X el li"
  -> "el X li", "el kilo / liter X" -> "kilo / liter el X", "el nesbe el fare2" -> "nesbet el fare2", "el total
  masroufe" -> "total masroufe".
- period: "fi / f" + a month or el sayf -> "bi"; a bare "el sayf" after a verb phrase -> "bel sayf"; "(bi / hal / el)
  osbou3 li mara2" -> "el jem3a li mar2it"; a bare "li mara2 / li ata3" with no time word before it -> "el shaher li
  mara2".
Lines that contain "emta bekhlas" are dropped (her ruling: never), as are the audit's "drop" lines.
"""

import hashlib
import re

MONTHS = (r"kanoun el tene|kanoun el awal|kanoun l awal|shbat|adar|nisan|nisen|ayyar|ayar|7zayran|tammouz|tamouz|ab|"
          r"ayloul|teshreen el awal|teshreen el tene|teshreen el tani")


def _pick(options: tuple[str, ...], key: str) -> str:
    return options[int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % len(options)]


def _sub(pattern: str, repl, text: str) -> str:
    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


def sarfet(q: str) -> str:
    return _sub(r"\bsarfet\b", "sarafet", q)


def li_ablo(q: str) -> str:
    return _sub(r"\bel (marra|mara|time|fetoura|fatoura) li ablo\b",
                lambda m: f"el {'fatoura' if m.group(1) in ('fetoura', 'fatoura') else 'marra'} "
                          f"{_pick(('li abla', 'el abla'), q)}", q)  # fmt: skip


def sa7abit(q: str) -> str:
    return _sub(r"\bsa7abit menne( aktar masari| aktar shi| aktar)?",
                lambda m: _pick(("sarafet aalayon aktar shi", "kalafoune aktar shi", "kalafuni aktar shi"), q), q)


def jaybte(q: str) -> str:
    return _sub(r"\b(adde|aday|adesh|addesh) (ra7|akhad) men jaybte\b", "aday sarafet", q)


def kam_money(q: str) -> str:
    return _sub(r"\bkam (dafa3et|dafa3t|sarafet|sarafto|dafa3to|total|masroufe|masrufe)\b", r"aday \1", q)


def rejected_word(q: str) -> str:
    q = _sub(r"\bmotawassit\b", "moyenne", q)
    q = _sub(r"\bli fetit\b", "li mar2it", q)
    return _sub(r"\bbaskawit\b", "baskot", q)


def dual(q: str) -> str:
    q = _sub(r"\b(2|tneen|tnen) (shhour|shouhour|shaher|shahr|eshor)\b", "shahrain", q)
    return _sub(r"\b(2 |tneen |tnen )(jem3a|jemaa|jem3at|osbou3)\b|\bosbou3en\b", "jem3ten", q)


def articles(q: str) -> str:
    q = _sub(r"\bbi bel miyye\b", "bel miyye", q)
    q = _sub(r"\bbi el ", "bel ", q)
    q = _sub(r"\b3al? el ", "3al ", q)
    q = _sub(r"\bl el ", "lal ", q)
    q = _sub(r"\bel nesbe el fare2\b", "nesbet el fare2", q)
    q = _sub(r"\bel total masroufe\b", "total masroufe", q)
    q = _sub(r"\bel (total|7a2|majmou3) el li\b", r"el \1 li", q)
    return _sub(r"\bel (kilo|liter|litr|litre) (?!el\b)([a-z0-9]+)", r"\1 el \2", q)


def period(q: str) -> str:
    q = _sub(rf"\b(fi|f) ({MONTHS})\b", r"bi \2", q)
    q = _sub(r"\b(fi|f) el sayf\b", "bel sayf", q)
    q = _sub(r"\b(sarafet|dafa3et|jebt|shtrit|shtarayt|rehet|akalt) el sayf\b", r"\1 bel sayf", q)
    q = _sub(r"\b(?:bi |hal |el )?osbou3 li mara2\b", "el jem3a li mar2it", q)
    # a bare "li mara2 / li ata3" (last ...) with no time word before it: last month
    def bare(m: re.Match) -> str:
        before = q[:m.start()].split()
        return m.group(0) if before and before[-1].lower() in _TIME else f"el shaher {m.group(0)}"

    return re.sub(r"\bli (?:mara2|ata3)\b", bare, q, flags=re.IGNORECASE)


# The words that already name the time before "li mara2" ("el jem3a li mar2it", "el khamis li mara2").
_TIME = frozenset({"shaher", "shahr", "chaher", "jem3a", "jemaa", "sene", "seneh", "marra", "mara", "wikend",
                   "weekend", "sayf", "shete", "tanayn", "taleta", "erb3a", "arb3a", "khamis", "sabet", "a7ad", "yom",
                   "nhar", "fasl", "sayfiye", "osbou3", "time", "fatoura", "fetoura"})


RULES = (("sarfet", sarfet), ("li_ablo", li_ablo), ("sa7abit", sa7abit), ("jaybte", jaybte),
         ("kam_money", kam_money), ("rejected_word", rejected_word), ("dual", dual), ("period", period),
         ("articles", articles))  # fmt: skip
DROP = re.compile(r"\bemta bekhlas\b|\bbkhallas\b", re.IGNORECASE)


def cleaned(question: str) -> tuple[str, list[str]]:
    """The question with every rule applied, and the names of the rules that changed it."""
    fired = []
    for name, rule in RULES:
        new = rule(question)
        if new != question:
            fired.append(name)
            question = new
    return question, fired
