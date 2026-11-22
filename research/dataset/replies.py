"""The user's own Arabizi replies for CLARIFY and REPLY examples (written by the user on 2026-11-08).

Qwen's questions read well, but its Arabizi replies did not ("kanoun el 2ammi aw kanoun el 7a2?"), and a reply is
what the fine-tuned model learns to say. So every Arabizi or mixed version of a CLARIFY or REPLY example gets one of
these lines instead, chosen by what the example is about. English versions keep Qwen's reply.
"""

import random
from dataclasses import replace

from research.dataset.catalogue import Catalogue
from research.dataset.checks import ALSO_ACCEPTED, Version, contains
from research.dataset.templates import Spec

GREETINGS = ("Marhaba", "Hi", "Bonjour")  # no kifak / kifik: the app does not know the user's gender yet
THANKS = ("Ya Hala", "Walaw", "Ta3a kel yom", "Ahla w Sahla")
PERIODS = {
    "kanoun": "azdak kanoun el awal aw kanoun el tene?",
    "awal el sene": "azdak awal 3 oshhor mn el sene?",
    "semester": "azdak ayya ashhor bel zabt?",  # the assistant's wording, following the user's "azdak" lines
    "hal fatra": "azdak mn emta la emta?",  # the user's line, 2026-11-15 (batch 3)
    "bi awal el shaher": "azdak mn emta la emta?",  # the same line for the beginning of the month (2026-11-16)
}
SHOP_QUESTIONS = ("aya mahal? fik taati tafasil aktar", "aya mahal azdak?", "aan aya ma7al aam tehki?")
SIGN_OFFS = ("Ya Hala", "Walaw")  # the user's, 2026-11-16, sometimes followed by "Bye!"


def users_reply(version: Version, spec: Spec, catalogue: Catalogue, rng: random.Random) -> Version:
    """The version with the user's reply when it is an Arabizi or mixed CLARIFY or REPLY; otherwise unchanged."""
    if spec.kind not in ("clarify", "reply") or version.language == "english":
        return version
    start = "CLARIFY" if spec.kind == "clarify" else "REPLY"
    return replace(version, reply=f"{start}: {_line(version.question, spec, catalogue, rng)}")


def _line(question: str, spec: Spec, catalogue: Catalogue, rng: random.Random) -> str:
    labels = spec.labels
    if spec.template == "C1":
        line = f"ma edert le2e fatoura 3an {_word_used(question, spec)}"
        suggestion = labels.get("suggestion")
        return line + (f", 2asdak {catalogue.item(suggestion).spellings[0]}?" if suggestion else "")
    if spec.template == "C2":
        suggestion = labels.get("suggestion")
        return f"ma la2ayt fatoura bi {labels['shop']}" + (f", 2asdak {suggestion}?" if suggestion else "")
    if spec.template == "C3":
        if labels.get("about") == "shop":  # a vague shop (the user's lines, 2026-11-16)
            return rng.choice(SHOP_QUESTIONS)
        return "7a2 shu? fik taati tafasil aktar"
    if spec.template == "C4":
        return PERIODS[labels["period"]]
    if spec.template == "C5":
        return f"ma edert le2e fatoura 3an {_word_used(question, spec)}"
    if spec.template == "C7":  # a lost receipt (the user's line, 2026-11-16)
        return "aymta w mn aya mahal jebto? aw shu fi yekun maktoub 3al fatoura?"
    if spec.template == "C8":  # which brand is better (the user's line, 2026-11-16)
        return "ma fie elak aya wahad ahsan, bas fie shuf aya wahad arkhas?"
    if spec.template == "C6":
        return "shu baddak ta3ref bel zabt?"
    if spec.template == "R1":
        if contains(question, "hon"):  # "enta hon?" (2026-11-16)
            return "eh hon, fiye se3dak?"
        return "sabah el nour" if contains(question, "sabah") else rng.choice(GREETINGS)
    if spec.template == "R2":
        return rng.choice(THANKS)
    if spec.template == "R3":
        return "fie jewbak 3an masroufak men fawatirak: adde sarfet, aa shu, wen"
    if spec.template == "R5":  # a sign-off
        return rng.choice(SIGN_OFFS) + (", Bye!" if rng.random() < 0.5 else "")
    if spec.template == "R4":
        return "hahaha, fie se3dak b shi tene?"
    raise ValueError(f"No reply written for {spec.template}")


def _word_used(question: str, spec: Spec) -> str:
    """The word the question used for the thing it asks about (one of the words it had to mention)."""
    words = spec.mentions[0]
    spelled = words + tuple(alias for word in words for alias in ALSO_ACCEPTED.get(word, ()))  # her spellings too
    return next((word for word in sorted(spelled, key=len, reverse=True) if contains(question, word)), words[-1])
