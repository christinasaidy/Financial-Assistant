"""The assistant's Arabizi replies in the form that matches the user's gender (batch 5, decided 2026-11-17).

Every gendered reply in batches 1-4 was written for a man ("baddak", "azdak"). Each one now has a woman's form and a
neutral form for users whose gender is not given; the neutral form avoids "you" (3 of the 5 friends who answered the
form preferred that). The forms are Christina's, approved on 2026-11-18:
research/dataset/raw/batch5/gender_forms_reviewed.md (table A for the stored replies; table B's new replies are
written in their right form when part 2 writes them), and table C (three more stored replies, approved the same
day; "tehki" / "tehke" are the same for a man and a woman, so "aan aya ma7al aam tehki?" needs no forms).
Table F (SMALLTALK) holds part 2's small-talk replies (approved 2026-11-20), used by research/dataset/smalltalk.py.

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

# Table F: the small-talk replies of batch 5 part 2, by their number in raw/batch5/smalltalk_replies_review.md
# (approved by Christina 2026-11-20, "all great", with her edits; #39-#41 "yes all good").
SMALLTALK = {
    1: Forms("REPLY: Marhaba! fiye se3dak b shi?",
              "REPLY: Marhaba! fiye se3dik b shi?",
              "REPLY: Marhaba! fi shi fiye se3ed fi?"),
    2: Forms("REPLY: Ahla! shu baddak ta3ref 3an fawatirak?",
              "REPLY: Ahla! shu baddik ta3rfe 3an fawatirik?",
              "REPLY: Ahla! shu fiye shouf bel fwatir?"),
    3: Forms("REPLY: Sabah el nour! bi shu se3dak?",
              "REPLY: Sabah el nour! bi shu se3dik?",
              "REPLY: Sabah el nour! bi shu fiye se3ed?"),
    4: Forms("REPLY: Bonjour! fiye se3dak b shi?",
              "REPLY: Bonjour! fiye se3dik b shi?",
              "REPLY: Bonjour! shu fiye a3mel?"),
    5: Forms("REPLY: Hi! badak tshuf shi bi fawatirak?",
              "REPLY: Hi! badik tshoufe shi bi fawatirik?",
              "REPLY: Hi! fi shi fiye shoufo bel fwatir?"),
    6: Forms("REPLY: Ahlen! eh hon, fiye se3dak?",
              "REPLY: Ahlen! eh hon, fiye se3dik?",
              "REPLY: Ahlen! eh hon, shu fiye a3mel?"),
    7: Forms("REPLY: Mnih merci, w enta? Fiye se3dak b shi?",
              "REPLY: Mnih merci, w ente? Fiye se3dik b shi?",
              "REPLY: Ana Mnih merci! Fi shi fiye se3ed fi?"),
    8: Forms("REPLY: Mnih, merci! bi shu se3dak?",
              "REPLY: Mnih, merci! bi shu se3dik?",
              "REPLY: Mnih, merci! bi shu fiye se3ed?"),
    9: Forms("REPLY: Hamdella, w enta kifak? Shu baddak ta3ref 3an masroufak?",
              "REPLY: Hamdella, w ente kifik? Shu baddik ta3rfe 3an masroufik?",
              "REPLY: Hamdella! Shu fiye shouf bel masruf?"),
    10: Forms("REPLY: Meshe el 7al, w enta? Badak tshuf adesh sarafet hal shaher?",
              "REPLY: Meshe el 7al, w ente? Badik tshoufe adesh sarafte hal shaher?",
              "REPLY: Meshe el 7al! Fiye 2oul adesh ra7 masari hal shaher."),
    11: Forms("REPLY: Tamem merci! Shu fiye a3melak?",
              "REPLY: Tamem merci! Shu fiye a3melik?",
              "REPLY: Tamem merci! Shu fiye a3mel?"),
    12: Forms("REPLY: Walaw", "REPLY: Walaw", "REPLY: Walaw"),
    13: Forms("REPLY: Ta3a kel yom", "REPLY: Ta3a kel yom", "REPLY: Ta3a kel yom"),
    14: Forms("REPLY: Ya Hala", "REPLY: Ya Hala", "REPLY: Ya Hala"),
    15: Forms("REPLY: Ahla w Sahla, w eza baddak shi ba3den ana hon",
              "REPLY: Ahla w Sahla, w eza baddik shi ba3den ana hon",
              "REPLY: Ahla w Sahla, w eza fi shi ba3den ana hon"),
    16: Forms("REPLY: 3a rase!", "REPLY: 3a rase!", "REPLY: aa rase!"),
    17: Forms("REPLY: Wala yhemmak! eza baddak shi tene ana hon",
              "REPLY: Wala yhemmik! eza baddik shi tene ana hon",
              "REPLY: Walaw! eza fi shi tene ana hon"),
    18: Forms("REPLY: Tekram 3aynak!", "REPLY: Tekram 3aynik!", "REPLY: Ya Hala, ayya wa2t!"),
    19: Forms("REPLY: Fiye 2elak adesh sarafet, 3a shu w wen, w se3er kel shi jebto, men fawatirak.",
              "REPLY: Fiye 2ellik adesh sarafte, 3a shu w wen, w se3er kel shi jebte, men fawatirik.",
              "REPLY: Fiye 2oul adesh ra7 masari, 3a shu w wen, w se3er kel shi, men el fwatir."),
    20: Forms("REPLY: Bjeweb 3an masroufak men fawatirak: adesh sarafet, wen, aymta, w wen arkhas.",
              "REPLY: Bjeweb 3an masroufik men fawatirik: adesh sarafte, wen, aymta, w wen arkhas.",
              "REPLY: Bjeweb 3an el masruf men el fwatir: adesh, wen, aymta, w wen arkhas."),
    21: Forms("REPLY: Es2alne 3an fawatirak: el majmou3, el categories, el ma7allet w el as3ar.",
              "REPLY: Es2aline 3an fawatirik: el majmou3, el categories, el ma7allet w el as3ar.",
              "REPLY: Fiye jeweb 3an el fwatir: el majmou3, el categories, el ma7allet w el as3ar."),
    22: Forms("REPLY: Ana Fatourati, bse3dak bi masarifak mn el fwatir.",
              "REPLY: Ana Fatourati, bse3dik bi masarifik mn el fwatir.",
              "REPLY: Ana Fatourati, bse3ed bel masarif mn el fwatir."),
    23: Forms("REPLY: hahaha, fie se3dak b shi tene?",
              "REPLY: hahaha, fie se3dik b shi tene?",
              "REPLY: hahaha, fi shi tene fie se3ed fi?"),
    24: Forms("REPLY: Hahaha! w eza baddak shi jad, ana hon",
              "REPLY: Hahaha! w eza baddik shi jad, ana hon",
              "REPLY: Hahaha! w eza fi shi jad, ana hon"),
    25: Forms("REPLY: Eh walla! Baddak shi tene?",
              "REPLY: Eh walla! Baddik shi tene?",
              "REPLY: Eh walla! Fi shi tene?"),
    26: Forms("REPLY: Hek tole3 bel fawatir! Fiye se3dak b shi tene?",
              "REPLY: Hek tole3 bel fawatir! Fiye se3dik b shi tene?",
              "REPLY: Hek tole3 bel fawatir! Fi shi tene fiye se3ed fi?"),
    27: Forms("REPLY: Ma3ak 7a2, kel shi sar ghale! Badak tshuf 3a shu ra7 aktar shi masari?",
              "REPLY: Ma3ik 7a2, kel shi sar ghale! Badik tshoufe 3a shu ra7 aktar shi masari?",
              "REPLY: Kel shi sar ghale! Fiye farje 3a shu ra7 aktar shi masari."),
    28: Forms("REPLY: Allah y3inak! Badak tshuf wen sarafet aktar shi?",
              "REPLY: Allah y3inik! Badik tshoufe wen sarafte aktar shi?",
              "REPLY: Ya latif! Fiye farje wen ra7 aktar shi masari."),
    29: Forms("REPLY: W nharak! Shu baddak ta3ref 3an fawatirak?",
              "REPLY: W nharik! Shu baddik ta3rfe 3an fawatirik?",
              "REPLY: Merci! fi shi fiye se3ed fi?"),
    30: Forms("REPLY: Merci! fiye se3dak b shi tene?",
              "REPLY: Merci! fiye se3dik b shi tene?",
              "REPLY: Merci! fi shi tene fiye se3ed fi?"),
    31: Forms("REPLY: Yala bye, aya wa2et aayiz shi ana hon!",
              "REPLY: Yala bye, aya wa2et aayze shi ana hon!",
              "REPLY: Yala bye, aya wa2et fi shi ana hon!"),
    32: Forms("REPLY: Yala bye, aya wa2et badak shi ana hon!",
              "REPLY: Yala bye, aya wa2et badik shi ana hon!",
              "REPLY: Yala bye, aya wa2et fi shi ana hon!"),
    33: Forms("REPLY: Ma3 el salame! w eza baddak shi ba3den ana hon",
              "REPLY: Ma3 el salame! w eza baddik shi ba3den ana hon",
              "REPLY: Ma3 el salame! w eza fi shi ba3den ana hon"),
    34: Forms("REPLY: Nshoufak!", "REPLY: Nshoufik!", "REPLY: Yala bye!"),
    35: Forms("REPLY: Bye, nharak sa3id!", "REPLY: Bye, nharik sa3id!", "REPLY: Bye, nhar sa3id!"),
    36: Forms("REPLY: Ana Fatourati, bse3dak bi masarifak mn el fwatir.",
              "REPLY: Ana Fatourati, bse3dik bi masarifik mn el fwatir.",
              "REPLY: Ana Fatourati, bse3ed bel masarif mn el fwatir."),
    37: Forms("REPLY: Eh, ana mosa3ed bjeweb 3an masrufak mn el fwatir.",
              "REPLY: Eh, ana mosa3ed bjeweb 3an masrufik mn el fwatir.",
              "REPLY: Eh, ana mosa3ed bjeweb 3an el masruf mn el fwatir."),
    38: Forms("REPLY: Ana Fatourati! B2ellak adesh sarafet w 3a shu, men fawatirak.",
              "REPLY: Ana Fatourati! B2ellik adesh sarafte w 3a shu, men fawatirik.",
              "REPLY: Ana Fatourati! B2oul adesh ra7 masari w 3a shu, men el fwatir."),
    39: Forms("REPLY: Salamtak! Inshalla ma fi shi kbir. W eza baddak shi, ana hon",
              "REPLY: Salamtik! Inshalla ma fi shi kbir. W eza baddik shi, ana hon",
              "REPLY: Inshalla ma fi shi kbir! W eza fi shi, ana hon"),
    40: Forms("REPLY: Ma3lesh, inshalla kel shi bi sir a7san! Fiye se3dak b shi?",
              "REPLY: Ma3lesh, inshalla kel shi bi sir a7san! Fiye se3dik b shi?",
              "REPLY: Ma3lesh, inshalla kel shi bi sir a7san! Fi shi fiye se3ed fi?"),
    41: Forms("REPLY: Alla y2awik! Eza baddak tshuf shi bi fawatirak, ana hon",
              "REPLY: Alla y2awike! Eza badik tshoufe shi bi fawatirik, ana hon",
              "REPLY: Alla y2awi! Eza fi shi bel fwatir, ana hon"),
}  # fmt: skip

# Table G: part 3's questions back when the user asks about rent or transfers they never entered (raw/batch5/
# deciding_review.md, approved by Christina 2026-11-20).
DECIDING = {
    "rent": (Forms("CLARIFY: Ma la2ayt ajar bi fwatirak, sajalto bi esem tene?",
                   "CLARIFY: Ma la2ayt ajar bi fwatirik, sajalte bi esem tene?",
                   "CLARIFY: Ma la2ayt ajar bel fwatir, msajal bi esem tene?"),
             Forms("CLARIFY: Ma la2ayt shi 3an el ajar, 7atayto bi category tenye?",
                   "CLARIFY: Ma la2ayt shi 3an el ajar, 7atayte bi category tenye?",
                   "CLARIFY: Ma la2ayt shi 3an el ajar, ma7tout bi category tenye?")),
    "transfer": (Forms("CLARIFY: Ma la2ayt ta7wilet bi fwatirak, sajalton bi esem tene?",
                       "CLARIFY: Ma la2ayt ta7wilet bi fwatirik, sajaltiyon bi esem tene?",
                       "CLARIFY: Ma la2ayt ta7wilet bel fwatir, msajalin bi esem tene?"),),
}

# Words that address a man. A reply holding one must have its forms above.
MASCULINE_WORDS = ("fik", "baddak", "azdak", "2asdak", "elak", "se3dak", "bse3dak", "jewbak", "masroufak", "masrufak",
                   "masarifak", "fawatirak", "jebto", "enta")  # fmt: skip
_MASCULINE = re.compile(r"(?<!\w)(" + "|".join(MASCULINE_WORDS) + r")(?!\w)", re.IGNORECASE)


def _pattern(template: str) -> re.Pattern:
    return re.compile("^" + re.escape(template).replace(r"\{x\}", "(?P<x>.+?)").replace(r"\{y\}", "(?P<y>.+?)") + "$")


_ALL_FORMS = (*FORMS, *SMALLTALK.values(), *(forms for group in DECIDING.values() for forms in group))
_PATTERNS = tuple((_pattern(forms.man), forms) for forms in _ALL_FORMS)


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


def _same(reply: str) -> Forms:
    return Forms(reply, reply, reply)


# A question that refers to something earlier with nothing earlier in the chat (C3) was always answered "7a2 shu?"
# (the price of what?), which fits a price question only. When it asks about a place, counts times, or asks about
# "the last one" without a price, it gets one of these instead, picked by its question (approved by Christina on
# 2026-11-21: "lets be creative fr").
REFERS_TO_PRICE = FORMS[0]
PLACE_QUESTIONS = (_same("CLARIFY: wayn bel zabt? shu esm el ma7al?"), _same("CLARIFY: ayya ma7al bel zabt?"),
                   FORMS[10], _same("CLARIFY: aan aya ma7al aam tehki?"))  # FORMS[10]: aya mahal azdak?
THING_QUESTIONS = (_same("CLARIFY: shu heda bl zabet?"), _same("CLARIFY: shu howe bl zabet?"),
                   _same("CLARIFY: aan shu aam tehki bl tehdid?"), _same("CLARIFY: 3an aya gharad aam tehke?"))
LAST_ONE_QUESTION = _same("CLARIFY: ekher wa7ad men shu?")
_PLACE = re.compile(r"\b(honik|hunik|there|ma7al|mahal|mat3am|mataam|restaurant|shop|place)\b")
_THING = re.compile(r"\b(shi|shaghle|wa7ad|wa7de|ha2o|ha2a|7a2o|azra2|blue|thing|one)\b")
_PRICE = re.compile(r"\b(ha2|ha2o|ha2a|7a2|7a2o|se3r|se3er|se3ro|se3ra|price|cost|kalafne|kalafetne|kalifne|"
                    r"tole3|total|pay|paid|spend|spent|dafa3et|sarafet|edfaa|jebt|jebet)\b")
_COUNT = re.compile(r"\b(kam marra|kam mara|marraat|marat)\b")
_LAST_ONE = re.compile(r"\b(ekher wa7ad|ekher wa7de|ekher shi|last one)\b")

# "No receipts from <shop>" (C2) in each of her forms, picked by the question (2026-11-21); the first is the stored one.
NO_RECEIPT_AT = ("ma la2ayt fatoura bi", "ma la2ayt wala fatoura bi", "ma la2ayt fatoura mn 3end", "ma la2ayt fatoura mn",
                 "ma l2it fatoura bi", "ma edert le2e fatoura bi")  # fmt: skip
_NO_RECEIPT_AT = re.compile(r"^CLARIFY: ma la2ayt fatoura bi (?P<x>.+?)(?:, 2asdak (?P<y>.+?)\?)?$")
_SUGGESTION = {Gender.MAN: ", 2asdak {y}?", Gender.WOMAN: ", 2asdik {y}?", Gender.NOT_GIVEN: ", ya3ne {y}?"}
_BASKAWIT = re.compile(r"\bbaskawit\b")  # her ruling 2026-11-16: biscuits / baskot, never baskawit


def _pick(options: tuple, question: str):
    return options[int(hashlib.sha256(question.encode("utf-8")).hexdigest(), 16) % len(options)]


def _refers_to(question: str) -> Forms:
    """The question back for a C3 question, by what it leaves unclear (the price question when unsure)."""
    words = " ".join(re.sub(r"[^\w\s]", " ", question.lower()).split())
    if _PLACE.search(words) and not _THING.search(words):
        return _pick(PLACE_QUESTIONS, question)
    if _COUNT.search(words):
        return _pick(THING_QUESTIONS, question)
    if _LAST_ONE.search(words) and not _PRICE.search(words):
        return LAST_ONE_QUESTION
    return REFERS_TO_PRICE


def _no_receipt_at(found: re.Match, gender: Gender, question: str) -> str:
    opening = _pick(NO_RECEIPT_AT, question) if question else NO_RECEIPT_AT[0]
    tail = _SUGGESTION[gender].format(y=found.group("y")) if found.group("y") else ""
    return f"CLARIFY: {opening} {found.group('x')}{tail}"


def for_gender(reply: str, gender: Gender, question: str = "") -> str:
    """The reply in the user's form. A reply with no gendered words is returned as it is; a masculine reply with no
    approved forms raises UnformedReply. The assistant's question about the period takes one of PERIOD_QUESTIONS,
    chosen by the user's `question` (the first form when none is given)."""
    reply = _BASKAWIT.sub("baskot", reply)
    if reply == PERIOD_QUESTIONS[0].man:
        pick = int(hashlib.sha256(question.encode("utf-8")).hexdigest(), 16) % len(PERIOD_QUESTIONS) if question else 0
        return PERIOD_QUESTIONS[pick].of(gender)
    if reply == REFERS_TO_PRICE.man and question:
        return _refers_to(question).of(gender)
    found = _NO_RECEIPT_AT.match(reply)
    if found:
        return _no_receipt_at(found, gender, question)
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
    ("mwa2a3a", "mwa2a3"), ("metwa23a", "metwa2i3"),  # "ma kent mwa2a3a": expecting, 2026-11-20
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
