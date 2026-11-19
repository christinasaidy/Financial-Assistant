"""The assistant's Arabizi replies in the form that matches the user's gender (batch 5, decided 2026-11-17).

Every gendered reply in batches 1-4 was written for a man ("baddak", "azdak"). Each one now has a woman's form and a
neutral form for users whose gender is not given; the neutral form avoids "you" (3 of the 5 friends who answered the
form preferred that). The forms are Christina's, approved on 2026-11-18:
research/dataset/raw/batch5/gender_forms_reviewed.md (table A for the stored replies; table B's new replies are
written in their right form when part 2 writes them), and table C (three more stored replies, approved the same
day; "tehki" / "tehke" are the same for a man and a woman, so "aan aya ma7al aam tehki?" needs no forms).

A reply that still has a masculine "you" word and no forms here is refused (UnformedReply), never passed on as it is.
"""

import hashlib
import re
from dataclasses import dataclass

from app.domain.assistant.prompt import Gender


class UnformedReply(ValueError):
    """A reply addressed to a man with no woman's or neutral form approved for it."""


@dataclass(frozen=True)
class Forms:
    """One reply in its three forms. {x} and {y} stand for an item or shop name the reply repeats."""

    man: str
    woman: str
    not_given: str

    def of(self, gender: Gender) -> str:
        return {Gender.MAN: self.man, Gender.WOMAN: self.woman, Gender.NOT_GIVEN: self.not_given}[gender]


# Table A (her rows 1-11) and row 12 as the stored replies spell them. The stored text is the man's form.
FORMS = (
    Forms("CLARIFY: 7a2 shu? fik taati tafasil aktar", "CLARIFY: 7a2 shu? fiki taate tafasil aktar",
          "CLARIFY: 7a2 shu bel zabt? fi tafasil aktar?"),
    Forms("REPLY: hahaha, fie se3dak b shi tene?", "REPLY: hahaha, fie se3dik b shi tene?",
          "REPLY: hahaha, fi shi tene fie se3ed fi?"),
    Forms("CLARIFY: shu baddak ta3ref bel zabt?", "CLARIFY: shu baddik ta3rfe bel zabt?",
          "CLARIFY: shu el ma2soud bel zabt?"),
    Forms("CLARIFY: azdak mn emta la emta?", "CLARIFY: azdik mn emta la emta?", "CLARIFY: mn emta la emta bel zabt?"),
    Forms("CLARIFY: azdak kanoun el awal aw kanoun el tene?", "CLARIFY: azdik kanoun el awal aw kanoun el tene?",
          "CLARIFY: kanoun el awal aw kanoun el tene?"),
    Forms("CLARIFY: azdak ayya ashhor bel zabt?", "CLARIFY: azdik ayya ashhor bel zabt?",
          "CLARIFY: ayya ashhor bel zabt?"),
    Forms("CLARIFY: azdak awal 3 oshhor mn el sene?", "CLARIFY: azdik awal 3 oshhor mn el sene?",
          "CLARIFY: awal 3 oshhor mn el sene?"),
    Forms("CLARIFY: ma fie elak aya wahad ahsan, bas fie shuf aya wahad arkhas?",
          "CLARIFY: ma fie elik aya wahad ahsan, bas fie shuf aya wahad arkhas?",
          "CLARIFY: ma fie 2oul aya wahad ahsan, bas fie shuf aya wahad arkhas?"),
    Forms("CLARIFY: ma la2ayt fatoura bi {x}, 2asdak {y}?", "CLARIFY: ma la2ayt fatoura bi {x}, 2asdik {y}?",
          "CLARIFY: ma la2ayt fatoura bi {x}, ya3ne {y}?"),
    Forms("CLARIFY: ma edert le2e fatoura 3an {x}, 2asdak {y}?", "CLARIFY: ma edert le2e fatoura 3an {x}, 2asdik {y}?",
          "CLARIFY: ma edert le2e fatoura 3an {x}, ya3ne {y}?"),
    Forms("CLARIFY: aya mahal azdak?", "CLARIFY: aya mahal azdik?", "CLARIFY: aya mahal bel zabt?"),
    Forms("REPLY: eh hon, fiye se3dak?", "REPLY: eh hon, fiye se3dik?", "REPLY: eh hon, shu fiye a3mel?"),
    # Table C.
    Forms("REPLY: fie jewbak 3an masroufak men fawatirak: adde sarfet, aa shu, wen",
          "REPLY: fie jewbik 3an masroufik men fawatirik: adde sarafte, aa shu, wen",
          "REPLY: fie jeweb 3an el masruf men el fwatir: adde, aa shu, wen"),
    Forms("CLARIFY: aymta w mn aya mahal jebto? aw shu fi yekun maktoub 3al fatoura?",
          "CLARIFY: aymta w mn aya mahal jebte? aw shu fi yekun maktoub 3al fatoura?",
          "CLARIFY: aymta w mn aya mahal? aw shu fi yekun maktoub 3al fatoura?"),
    Forms("CLARIFY: aya mahal? fik taati tafasil aktar", "CLARIFY: aya mahal? fiki taate tafasil aktar",
          "CLARIFY: aya mahal bel zabt?"),
)

# Words that address a man. A reply holding one must have its forms above.
MASCULINE_WORDS = ("fik", "baddak", "azdak", "2asdak", "elak", "se3dak", "bse3dak", "jewbak", "masroufak", "masrufak",
                   "masarifak", "fawatirak", "jebto", "enta")  # fmt: skip
_MASCULINE = re.compile(r"(?<!\w)(" + "|".join(MASCULINE_WORDS) + r")(?!\w)", re.IGNORECASE)


def _pattern(template: str) -> re.Pattern:
    return re.compile("^" + re.escape(template).replace(r"\{x\}", "(?P<x>.+?)").replace(r"\{y\}", "(?P<y>.+?)") + "$")


_PATTERNS = tuple((_pattern(forms.man), forms) for forms in FORMS)


# The assistant's question about the period, in Christina's forms (2026-11-19: "don't just have the model answer azdak
# mn emta la emta each time"). A stored reply with the first form gets one of these, picked by its question, so the
# same question always gets the same one.
PERIOD_QUESTIONS = (
    Forms("CLARIFY: azdak mn emta la emta?", "CLARIFY: azdik mn emta la emta?", "CLARIFY: mn emta la emta bel zabt?"),
    Forms("CLARIFY: men aymata la aymata azdak?", "CLARIFY: men aymata la aymata azdik?",
          "CLARIFY: men aymata la aymata bel zabt?"),
    Forms("CLARIFY: 3an aya fatra 7abeb ta3ref?", "CLARIFY: 3an aya fatra 7abe ta3rfe?", "CLARIFY: 3an aya fatra bel zabt?"),
    Forms("CLARIFY: aan aya fatra baddak ta3rif?", "CLARIFY: aan aya fatra baddik ta3irfe?",
          "CLARIFY: 3an aya fatra bel zabt?"),
)  # fmt: skip


def for_gender(reply: str, gender: Gender, question: str = "") -> str:
    """The reply in the user's form. A reply with no gendered words is returned as it is; a masculine reply with no
    approved forms raises UnformedReply. The assistant's question about the period takes one of PERIOD_QUESTIONS,
    chosen by the user's `question` (the first form when none is given)."""
    if reply == PERIOD_QUESTIONS[0].man:
        pick = int(hashlib.sha256(question.encode("utf-8")).hexdigest(), 16) % len(PERIOD_QUESTIONS) if question else 0
        return PERIOD_QUESTIONS[pick].of(gender)
    for pattern, forms in _PATTERNS:
        found = pattern.match(reply)
        if found:
            return forms.of(gender).format(**found.groupdict())
    if _MASCULINE.search(reply):
        raise UnformedReply(f"no woman's or neutral form approved for: {reply}")
    return reply


# The user's own words for "I" that change with who is speaking (Christina, 2026-11-19; table D of
# gender_forms_reviewed.md). The questions were written before users had a gender, so a man's question could say
# "def3a"; each word becomes its counterpart for the user's gender. "dafa3et" / "dafa3it" are the same for both.
SPEAKER_WORDS = (  # (woman, man)
    ("def3a", "defe3"), ("defaa", "defe3"),
    ("7esa", "7eses"), ("7ase", "7ases"), ("7asi", "7ases"), ("hesa", "heses"), ("hase", "hases"), ("hasi", "hasis"),
    ("meshtreye", "meshtere"), ("meshtriye", "meshteri"),
    ("3ayshe", "3ayesh"), ("aayshe", "aayesh"),  # living ("3ayesh bi Total"), 2026-11-19
)  # fmt: skip
_TO_MAN = {woman: man for woman, man in SPEAKER_WORDS}
_TO_WOMAN = {man: woman for woman, man in reversed(SPEAKER_WORDS)}  # defe3 -> def3a, 7eses -> 7esa (the first listed)


def _speaker_pattern(words) -> re.Pattern:
    return re.compile(r"(?<!\w)(" + "|".join(sorted(words, key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)


_WOMAN_WORDS, _MAN_WORDS = _speaker_pattern(_TO_MAN), _speaker_pattern(_TO_WOMAN)


def question_for_gender(question: str, gender: Gender) -> str:
    """The user's question with "I" words in their own gender's form; unchanged when the gender is not given."""
    if gender is Gender.NOT_GIVEN:
        return question
    pattern, table = (_WOMAN_WORDS, _TO_MAN) if gender is Gender.MAN else (_MAN_WORDS, _TO_WOMAN)

    def swap(found: re.Match) -> str:
        word = table[found.group(1).lower()]
        return word.capitalize() if found.group(1)[0].isupper() else word

    return pattern.sub(swap, question)
