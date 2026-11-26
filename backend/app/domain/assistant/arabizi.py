"""Checking a Standard answer against the owner's Lebanese Arabizi rulings (2026-11-23).

The words come from the generated pack (backend/app/assistant_assets/arabizi/forms.json), never from here. The checks
are the ones the research dataset applies to its approved answers (research/dataset/answers_build.py): a rejected
spelling, or a word of the other gender, as a whole word in any case. "Neutral" (no gender given) allows the words of
neither. A word the user wrote, or a name from the data (a shop called "Sakin"), is never held against the answer:
names and the user's own spellings are not corrected.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.domain.users.user import Gender


class Address(StrEnum):
    """Which reply forms to use, from the gender the user chose at sign-up (never guessed from a name)."""

    MAN = "man"
    WOMAN = "woman"
    NEUTRAL = "neutral"  # not given, or "prefer not to say": forms that avoid addressing "you"


def address_for(gender: Gender | None) -> Address:
    """The gender the user chose at sign-up; neutral for "prefer not to say" and for accounts made before it."""
    return {Gender.MALE: Address.MAN, Gender.FEMALE: Address.WOMAN}.get(gender, Address.NEUTRAL)


@dataclass(frozen=True)
class ArabiziWords:
    rejected: frozenset[str]  # spellings the owner ruled out
    man_only: frozenset[str]  # words only said to a man ("sarafet")
    woman_only: frozenset[str]  # words only said to a woman ("sarafte")


def problems(text: str, words: ArabiziWords, address: Address, allowed_text: Iterable[str] = ()) -> list[str]:
    """What is wrong with the answer by the rulings; empty when nothing is."""
    allowed = " ".join(allowed_text)
    found = []
    rejected = _whole_words(text, words.rejected, allowed)
    if rejected:
        found.append(f"rejected spelling {', '.join(rejected)}")
    other = {Address.MAN: words.woman_only, Address.WOMAN: words.man_only,
             Address.NEUTRAL: words.man_only | words.woman_only}[address]  # fmt: skip
    wrong = _whole_words(text, other, allowed)
    if wrong:
        found.append(f"words not for a {address.value} reader: {', '.join(wrong)}" if address is not Address.NEUTRAL
                     else f"gendered words, but the user's gender is not given: {', '.join(wrong)}")  # fmt: skip
    return found


def _whole_words(text: str, words: Iterable[str], allowed: str) -> list[str]:
    return sorted(
        word for word in words if _has(text, word) and not _has(allowed, word)
    )


def _has(text: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) is not None
