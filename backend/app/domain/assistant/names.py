"""Finding the user's own spelling of a vendor, item or category (the Standard mode's find_names tool, 2026-11-23).

The user types "spineys" or "zwz"; the receipts say "Spinneys" or "Zaatar w Zeit". A query must use the receipts'
exact spelling, so the name is looked up first, in every name of the user's confirmed receipts (not only the newest
100 the Beta prompt lists).
- Only the same spelling counts as found: the same letters ignoring case, spaces and punctuation ("spinneys" finds
  "Spinneys", "zaatar w zeit" finds "Zaatar W Zeit").
- Anything else is at most a suggestion: similar is not the same shop ("Spinneys" and "Spinneys Achrafieh" may be
  one shop or two), so a suggestion is offered to the user to confirm, never used as if it were found.
- Nothing found or suggested does not prove the user never bought there: the name may be spelled very differently,
  or the receipt may not be confirmed yet.
"""

import difflib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

MAX_SUGGESTIONS = 5
SIMILARITY = 0.6  # difflib's ratio; a starting value, not a measured one
MIN_FUZZY_LENGTH = 4  # shorter names are suggested only as a whole word of a longer one
_NOT_WORD = re.compile(r"[\W_]+")


class NameKind(StrEnum):
    VENDOR = "vendor"
    ITEM = "item"
    CATEGORY = "category"


class MatchStatus(StrEnum):
    FOUND = "found"  # exactly one name with this spelling
    AMBIGUOUS = "ambiguous"  # more than one (e.g. "Pharmacie Mazen" and "pharmacie mazen" saved as two vendors)
    SUGGESTIONS = "suggestions"  # none with this spelling, some similar: ask the user which, if any
    NOT_FOUND = "not_found"  # none with this spelling and none similar


@dataclass(frozen=True)
class KnownName:
    name: str
    receipts: int  # how many confirmed receipts use it
    last_used: date | None


@dataclass(frozen=True)
class NameMatch:
    status: MatchStatus
    names: tuple[KnownName, ...]  # FOUND / AMBIGUOUS: the exact spellings; SUGGESTIONS: the similar names


def spelling_key(name: str) -> str:
    """What two spellings must share to be the same name: letters and digits, ignoring case, spaces and punctuation."""
    return _NOT_WORD.sub(" ", name.casefold()).strip()


def match_name(query: str, known: Sequence[KnownName]) -> NameMatch:
    key = spelling_key(query)
    if not key:
        return NameMatch(MatchStatus.NOT_FOUND, ())
    exact = tuple(name for name in known if spelling_key(name.name) == key)
    if len(exact) == 1:
        return NameMatch(MatchStatus.FOUND, exact)
    if exact:
        return NameMatch(MatchStatus.AMBIGUOUS, exact)
    scored = [(score, name) for name in known if (score := _similarity(key, spelling_key(name.name))) >= SIMILARITY]
    scored.sort(key=lambda pair: (-pair[0], -pair[1].receipts, pair[1].name))
    suggestions = tuple(name for _, name in scored[:MAX_SUGGESTIONS])
    return NameMatch(MatchStatus.SUGGESTIONS if suggestions else MatchStatus.NOT_FOUND, suggestions)


def _similarity(query: str, name: str) -> float:
    if not name:
        return 0.0
    words = name.split()
    if query in words or set(query.split()) <= set(words):  # "spinneys" in "spinneys achrafieh": a whole word
        return 0.9
    if len(query) < MIN_FUZZY_LENGTH:  # "tea" is too short to be similar to anything by spelling ("steak")
        return 0.0
    whole = difflib.SequenceMatcher(None, query, name).ratio()
    best_word = max(difflib.SequenceMatcher(None, query, word).ratio() for word in words)
    return max(whole, best_word)
