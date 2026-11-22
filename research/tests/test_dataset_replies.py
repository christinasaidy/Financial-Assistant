"""The user's own Arabizi replies for CLARIFY and REPLY examples (written by the user on 2026-11-08). Nothing here
touches a database or a model."""

import random

import pytest

from research.dataset.catalogue import load_catalogue
from research.dataset.checks import Version
from research.dataset.replies import THANKS, users_reply
from research.dataset.templates import Spec

CATALOGUE = load_catalogue()


def clarify(template: str, words: tuple[str, ...] = (), **labels) -> Spec:
    return Spec(template, "clarify", "", None, (words,) if words else (), "hint", labels=labels)


def replied(spec: Spec, question: str, language: str = "arabizi", qwen: str = "CLARIFY: qwen's words") -> str:
    return users_reply(Version(language, question, qwen), spec, CATALOGUE, random.Random(1)).reply


def test_an_unknown_item_names_the_word_the_user_wrote_and_suggests_the_closest_one():
    spec = clarify("C1", ("oil", "zayt", "zet"), item="oil", suggestion="olive oil")
    assert replied(spec, "adde sarfet 3al zayt hal shaher?") == (
        "CLARIFY: ma edert le2e fatoura 3an zayt, 2asdak zeit zaytoun?")
    alone = clarify("C1", ("oil", "zayt", "zet"), item="oil", suggestion=None)
    assert replied(alone, "adde sarfet 3al zet?") == "CLARIFY: ma edert le2e fatoura 3an zet"


def test_an_unknown_shop_is_named_as_the_shop_is_called():
    spec = clarify("C2", ("Spinneys", "spinnys"), shop="Spinneys", suggestion=None)
    assert replied(spec, "adde sarfet bi spinnys?") == "CLARIFY: ma la2ayt fatoura bi Spinneys"
    near = clarify("C2", ("Spinneys", "spinnys"), shop="Spinneys", suggestion="Carrefour")
    assert replied(near, "adde sarfet bi spinnys?") == "CLARIFY: ma la2ayt fatoura bi Spinneys, 2asdak Carrefour?"


@pytest.mark.parametrize(("period", "expected"), [
    ("kanoun", "CLARIFY: azdak kanoun el awal aw kanoun el tene?"),
    ("awal el sene", "CLARIFY: azdak awal 3 oshhor mn el sene?"),
    ("semester", "CLARIFY: azdak ayya ashhor bel zabt?"),
])  # fmt: skip
def test_an_unclear_period_is_asked_back(period, expected):
    assert replied(clarify("C4", (period,), period=period), f"adde sarfet bi {period}?") == expected


def test_nothing_to_refer_to_gifts_and_repairs_and_say_again():
    assert replied(clarify("C3"), "adde ken 7a2 ekher wa7ad") == "CLARIFY: 7a2 shu? fik taati tafasil aktar"
    repairs = clarify("C5", ("tasli7", "repairs"), group="repairs")
    assert replied(repairs, "adde dafa3et 3al tasli7?") == "CLARIFY: ma edert le2e fatoura 3an tasli7"
    assert replied(clarify("C6"), "ma fhemet") == "CLARIFY: shu baddak ta3ref bel zabt?"


def test_replies_use_the_users_lines():
    def reply(template: str, question: str) -> str:
        return replied(Spec(template, "reply", "", None, (), "hint", labels={}), question, qwen="REPLY: qwen")

    assert reply("R1", "sabah el kheir") == "REPLY: sabah el nour"
    assert reply("R1", "hi kifak") in ("REPLY: Marhaba", "REPLY: Hi", "REPLY: Bonjour")
    assert reply("R2", "merci ktir") in tuple(f"REPLY: {line}" for line in THANKS)
    assert reply("R3", "shu fik ta3mel?") == "REPLY: fie jewbak 3an masroufak men fawatirak: adde sarafet, aa shu, wen"  # 2026-11-23
    assert reply("R4", "wow ma kent metwa23a") == "REPLY: hahaha, fie se3dak b shi tene?"


def test_mixed_versions_get_them_too_and_english_versions_and_queries_keep_qwens():
    spec = clarify("C6")
    assert replied(spec, "i didn't get it, ma fhemet", language="mixed") == "CLARIFY: shu baddak ta3ref bel zabt?"
    assert replied(spec, "I didn't get that", language="english") == "CLARIFY: qwen's words"
    query = Spec("T1", "sql", "", "SELECT 1", ())
    assert users_reply(Version("arabizi", "adde sarafet?"), query, CATALOGUE, random.Random(1)).reply is None


# Her spellings in the batch-1 rewrites (2026-11-22): the checks accept them and the ask-back repeats them.
C5_GIFTS = ("hadeye", "hadaya", "hdaya", "gifts", "gift")  # templates.c5_no_such_items
C5_REPAIRS = ("tasli7", "tesli7", "repairs", "siyene", "siyane", "maintenance")


@pytest.mark.parametrize(("words", "question", "word"), [
    (C5_GIFTS, "adesh kalafoune el hadeya li jebton?", "hadeya"),
    (C5_GIFTS, "adday dafa3et 3al hdeye?", "hdeye"),
    (C5_REPAIRS, "aday dafa3et 3al tosli7?", "tosli7"),
])  # fmt: skip
def test_her_spelling_of_gift_or_repairs_passes_the_checks_and_is_repeated_back(words, question, word):
    from research.dataset.checks import mentions

    assert mentions(question, words)
    group = "gifts" if words is C5_GIFTS else "repairs"
    assert replied(clarify("C5", words, group=group), question) == f"CLARIFY: ma edert le2e fatoura 3an {word}"


def test_her_spelling_of_the_season_passes_the_checks():
    from research.dataset.checks import mentions

    assert mentions("baddi majmou3 masroufe hal fasel", ("semester", "fasl"))
    assert not mentions("baddi majmou3 masroufe hal shaher", ("semester", "fasl"))


def test_no_spelling_is_listed_twice_in_also_accepted():
    """A repeated key silently drops the first entry (2026-11-22: "li mara2" lost her "ekher l shaher" that way)."""
    import ast
    from pathlib import Path

    from research.dataset import checks

    tree = ast.parse(Path(checks.__file__).read_text(encoding="utf-8"))
    table = next(node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                 and any(getattr(t, "id", None) == "ALSO_ACCEPTED" for t in node.targets))  # fmt: skip
    keys = [key.value for key in table.keys]
    assert len(keys) == len(set(keys)), sorted({k for k in keys if keys.count(k) > 1})
    assert checks.ALSO_ACCEPTED["li mara2"] == ("ekher l shaher", "el shaher li ra7")
