"""Reading the question writer's reply, and the checks that drop a version (approved by the user on 2026-11-05/07).

A version is dropped, with the reason logged, when:
- it does not contain one word of each group the question must mention (its item, shop, category or period);
- it is a T9 question (no brand) that names one of its item's brands, unless people use that brand as the item's
  own name (kleenex, nutella: listed among the item's spellings);
- it has Arabic script;
- it is blank or longer than 300 characters;
- a follow-up's earlier question misses what it asked (its item, shop or period; a plural is fine);
- its Arabizi buys a service or bill (jebt el ghasil sayara);
- its reply does not start the way its kind needs (CLARIFY: / REPLY:), or a REPLY states a number
  (digits inside a word are Arabizi letters, not numbers);
- a follow-up has no earlier question;
- it is a near-duplicate of a test question (difflib similarity of at least 0.85 after lowercasing and removing
  punctuation), so no test question leaks into training.
"""

import difflib
import json
import re
from dataclasses import dataclass

from research.dataset.catalogue import Catalogue
from research.dataset.templates import Spec

MAX_LENGTH = 300
# Spellings accepted by the checks but not listed in the period words, so the saved prompts (and replays) stay the same.
# approved 2026-11-14; 3elkit (3elkit Trident), abl mbereh (the day before yesterday), la hadit hala2 and sar
# masroufe (so far), ekher l shaher (last month) and kanoun l awal (December) 2026-11-20, her spellings; the batch-1
# cleanup's duals (shahrain, jem3ten: "2") and "nesbet el fare2" (the percent) 2026-11-21; her spellings of gift,
# repairs and season in the batch-1 rewrites (hadeya, hdeye, tosli7, fasel) and "hayda l shaher", "tlet", "ma3jun snen" (part 4) 2026-11-22; her word list's spellings
# (everyday words, her review 2026-11-22: "keep them, whats the harm")
ALSO_ACCEPTED = {"mbere7": ("mberha", "mberh"), "3elke": ("3elkit",), "abel mbereh": ("abl mbereh",),
                 "abel mbere7": ("abl mbere7",), "la hala2": ("la hadit hala2",), "li mara2": ("ekher l shaher", "el shaher li ra7"),
                 "sar le": ("sar masroufe",), "kanoun el awal": ("kanoun l awal",), "tneen": ("shahrain", "jem3ten"),
                 "bel miyye": ("nesbet",), "el ablo": ("bel ablo",), "el ishtirak": ("bel ishtirak",),
                 "hadeye": ("hadeya", "hdeye"), "tasli7": ("tosli7",), "fasl": ("fasel",), "hal shaher": ("hayda l shaher", "men awal el shaher la lyom"), "tlete": ("tlet",),
                 "ma3jun snan": ("ma3jun snen",), "el shaher li ata3": ("el shaher li ra7",),
                 "el jem3a el madye": ("el jem3a li ra7et",), "el sene li mar2it": ("el sene li ra7et",),
                 "el sene el madye": ("el sene el madiye",), "borto2an": ("bort2an",), "7amod": ("7amed",),
                 "lahme mafrume": ("lahme mafroume",), "restaurant": ("resto",), "dishwashing liquid": ("dish soap",),
                 "nail polish": ("manicure",), "Carrefour": ("Carefour",)}
NEAR_DUPLICATE = 0.85
LANGUAGES = ("arabizi", "mixed", "english")
# Services and bills are paid for, not bought ("jebt el ghasil sayara" makes no sense); a phone recharge and a cinema
# ticket are bought (decided with the user on 2026-11-08).
SERVICES = frozenset({"car wash", "electricity bill", "internet", "generator subscription", "gym membership", "parking",
                      "delivery fee", "streaming subscription", "music subscription"})
_BUYING = re.compile(r"\b(jebt|jebet|jibt|jebto|jebta|jebton|shtarayt|shtarit|shtrit|shetrit|chtarit|shtarayto|"
                     r"shtarayta|shtarayton|shtrito)\b")
# A number stands alone: digits inside a word are Arabizi letters (3afak, b2a2ak), found 2026-11-08.
_NUMBER = re.compile(r"(?<![^\W\d_])\d+(?![^\W\d_])")
_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


@dataclass(frozen=True)
class Version:
    language: str
    question: str
    reply: str | None = None  # CLARIFY: ... or REPLY: ...
    first: str | None = None  # a follow-up's earlier question


class UnreadableReply(ValueError):
    pass


def read_versions(text: str) -> list[Version]:
    """The versions in the writer's JSON. Tolerates a ```json fence around it; anything else unreadable raises."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise UnreadableReply(f"not JSON: {exc.msg}") from exc
    entries = data.get("versions") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise UnreadableReply('no "versions" list')
    versions = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("question"), str):
            raise UnreadableReply("a version without a question")
        versions.append(Version(
            language=str(entry.get("language", "")).strip().lower(), question=entry["question"].strip(),
            reply=entry["reply"].strip() if isinstance(entry.get("reply"), str) else None,
            first=entry["first"].strip() if isinstance(entry.get("first"), str) else None,
        ))  # fmt: skip
    return versions


def normalized(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def contains(text: str, word: str) -> bool:
    """Whether a word or phrase appears as a whole (Arabizi digits count as letters: '3asal', 'ma7al')."""
    if not normalized(word):  # a symbol such as $ or %: as written
        return word in text
    pattern = r"(?<![a-z0-9])" + re.escape(normalized(word)) + r"(?![a-z0-9])"
    return re.search(pattern, normalized(text)) is not None


def mentions(text: str, words: tuple[str, ...]) -> bool:
    """Whether the text has one of the words, its plural, or a spelling in ALSO_ACCEPTED."""
    accepted = words + tuple(alias for word in words for alias in ALSO_ACCEPTED.get(word, ()))
    return any(contains(text, word) or contains(text, word + "s") for word in accepted)


def problems(version: Version, spec: Spec, catalogue: Catalogue, test_questions: tuple[str, ...] = ()) -> list[str]:
    found = []
    question = version.question
    if version.language not in LANGUAGES:
        found.append(f"unknown language {version.language!r}")
    if not question or len(question) > MAX_LENGTH:
        found.append("blank or too long")
    for text in (question, version.reply or "", version.first or ""):
        if _ARABIC.search(text):
            found.append("Arabic script")
            break
    for words in spec.mentions:  # plurals allowed, as for the earlier question ("kilos", "board games"; 2026-11-14)
        if not mentions(question, words):
            found.append(f"does not mention any of: {', '.join(words[:4])}")
    if spec.template == "T9":  # its own item's brands only: some brands are ordinary words ("fine", "always")
        item = catalogue.item(spec.labels["item"])
        brands = set(item.brands) | {word for words in item.brand_words.values() for word in words}
        brands -= set(item.spellings)  # a brand people use as the item's own name ("kleenex") is not naming a brand
        named = sorted(brand for brand in brands if contains(question, brand))
        if named:
            found.append(f"a T9 question names a brand: {', '.join(named)}")
    if spec.kind in ("clarify", "reply"):
        start = "CLARIFY:" if spec.kind == "clarify" else "REPLY:"
        if not version.reply or not version.reply.startswith(start) or len(version.reply) <= len(start) + 1:
            found.append(f"the reply does not start with {start}")
        elif spec.kind == "reply" and _NUMBER.search(version.reply):
            found.append("a REPLY states a number")
    if spec.base is not None and not version.first:
        found.append("a follow-up without its earlier question")
    elif spec.base is not None:  # it is paired with the SQL of what it should ask, so it must ask that (2026-11-08)
        for words in spec.base.mentions:
            if not mentions(version.first, words):
                found.append(f"the earlier question does not mention any of: {', '.join(words[:4])}")
    if version.language != "english":
        items = {spec.labels.get("item"), spec.base.labels.get("item") if spec.base else None} & SERVICES
        if items and _BUYING.search(normalized(question + " " + (version.first or ""))):
            found.append(f"buys a service: {', '.join(sorted(items))}")
    duplicate = near_duplicate(question, test_questions)
    if duplicate:
        found.append(f"near-duplicate of a test question: {duplicate}")
    return found


def near_duplicate(question: str, test_questions: tuple[str, ...]) -> str | None:
    mine = normalized(question)
    for test in test_questions:
        if difflib.SequenceMatcher(None, mine, normalized(test)).ratio() >= NEAR_DUPLICATE:
            return test
    return None
