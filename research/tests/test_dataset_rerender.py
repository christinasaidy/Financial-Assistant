"""Batch 5's gender forms and the rebuilding of every stored example with today's prompt. The forms are Christina's,
approved on 2026-11-18 (research/dataset/raw/batch5/gender_forms_reviewed.md); do not change an expected value to
make a test pass."""

from datetime import date

import pytest

from app.domain.assistant.prompt import Exchange, Gender, UserNames, build_prompt
from research.dataset.genders import UnformedReply, for_gender
from research.dataset.rerender import UnreadablePrompt, read_prompt, rerender, without_batch5_lines

NAMES = UserNames(items=["sushi", "yoga mat"], vendors=["O&C", "Sushi Co"], categories=["Dining", "Groceries"])
TODAY = date(2026, 12, 9)
WOMAN, MAN, NOT_GIVEN = 46, 45, 43  # users of batch 4, by gender_of

# Her table A, with names filled in where the reply repeats one: (man, woman, neutral).
TABLE_A = [
    ("CLARIFY: 7a2 shu? fik taati tafasil aktar", "CLARIFY: 7a2 shu? fiki taate tafasil aktar",
     "CLARIFY: 7a2 shu bel zabt? fi tafasil aktar?"),
    ("REPLY: hahaha, fie se3dak b shi tene?", "REPLY: hahaha, fie se3dik b shi tene?",
     "REPLY: hahaha, fi shi tene fie se3ed fi?"),
    ("CLARIFY: shu baddak ta3ref bel zabt?", "CLARIFY: shu baddik ta3rfe bel zabt?", "CLARIFY: shu el ma2soud bel zabt?"),
    ("CLARIFY: azdak mn emta la emta?", "CLARIFY: azdik mn emta la emta?", "CLARIFY: mn emta la emta bel zabt?"),
    ("CLARIFY: azdak kanoun el awal aw kanoun el tene?", "CLARIFY: azdik kanoun el awal aw kanoun el tene?",
     "CLARIFY: kanoun el awal aw kanoun el tene?"),
    ("CLARIFY: azdak ayya ashhor bel zabt?", "CLARIFY: azdik ayya ashhor bel zabt?", "CLARIFY: ayya ashhor bel zabt?"),
    ("CLARIFY: azdak awal 3 oshhor mn el sene?", "CLARIFY: azdik awal 3 oshhor mn el sene?",
     "CLARIFY: awal 3 oshhor mn el sene?"),
    ("CLARIFY: ma fie elak aya wahad ahsan, bas fie shuf aya wahad arkhas?",
     "CLARIFY: ma fie elik aya wahad ahsan, bas fie shuf aya wahad arkhas?",
     "CLARIFY: ma fie 2oul aya wahad ahsan, bas fie shuf aya wahad arkhas?"),
    ("CLARIFY: ma la2ayt fatoura bi Sushi Co, 2asdak Crepaway?", "CLARIFY: ma la2ayt fatoura bi Sushi Co, 2asdik Crepaway?",
     "CLARIFY: ma la2ayt fatoura bi Sushi Co, ya3ne Crepaway?"),
    ("CLARIFY: ma edert le2e fatoura 3an yoga mat, 2asdak tapis?",
     "CLARIFY: ma edert le2e fatoura 3an yoga mat, 2asdik tapis?", "CLARIFY: ma edert le2e fatoura 3an yoga mat, ya3ne tapis?"),
    ("CLARIFY: aya mahal azdak?", "CLARIFY: aya mahal azdik?", "CLARIFY: aya mahal bel zabt?"),
    ("REPLY: eh hon, fiye se3dak?", "REPLY: eh hon, fiye se3dik?", "REPLY: eh hon, shu fiye a3mel?"),  # her row 12
    # Her table C.
    ("REPLY: fie jewbak 3an masroufak men fawatirak: adde sarfet, aa shu, wen",
     "REPLY: fie jewbik 3an masroufik men fawatirik: adde sarafte, aa shu, wen",
     "REPLY: fie jeweb 3an el masruf men el fwatir: adde, aa shu, wen"),
    ("CLARIFY: aymta w mn aya mahal jebto? aw shu fi yekun maktoub 3al fatoura?",
     "CLARIFY: aymta w mn aya mahal jebte? aw shu fi yekun maktoub 3al fatoura?",
     "CLARIFY: aymta w mn aya mahal? aw shu fi yekun maktoub 3al fatoura?"),
    ("CLARIFY: aya mahal? fik taati tafasil aktar", "CLARIFY: aya mahal? fiki taate tafasil aktar",
     "CLARIFY: aya mahal bel zabt?"),
]  # fmt: skip


@pytest.mark.parametrize("man, woman, neutral", TABLE_A)
def test_each_reply_takes_the_form_of_the_users_gender(man, woman, neutral):
    assert for_gender(man, Gender.MAN) == man
    assert for_gender(man, Gender.WOMAN) == woman
    assert for_gender(man, Gender.NOT_GIVEN) == neutral


@pytest.mark.parametrize("reply", ["CLARIFY: ma edert le2e fatoura 3an gifts", "REPLY: Ya Hala", "REPLY: sabah el nour",
                                   "UNSUPPORTED", "SELECT 1", "CLARIFY: Which shop do you mean?",
                                   "CLARIFY: aan aya ma7al aam tehki?"])  # "tehki" is not gendered (Christina) # fmt: skip
def test_a_reply_with_no_gendered_word_stays_as_it_is(reply):
    for gender in Gender:
        assert for_gender(reply, gender) == reply


@pytest.mark.parametrize("reply", ["REPLY: shu baddak?", "CLARIFY: fik t2elle aya mahal?", "REPLY: enta hon?"])  # fmt: skip
def test_a_masculine_reply_with_no_approved_forms_is_refused_even_for_a_man(reply):
    for gender in Gender:
        with pytest.raises(UnformedReply):
            for_gender(reply, gender)


def old_example(user: int, question: str, reply: str, history=(), language="arabizi") -> dict:
    """An example as batches 1-4 stored it: no gender line, no new rule."""
    prompt = without_batch5_lines(build_prompt(question, NAMES, TODAY, history, gender=Gender.MAN))
    return {"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}],
            "labels": {"user": user, "language": language, "spec": "b4-x-1"}}  # fmt: skip


def test_a_prompt_reads_back_into_the_parts_it_was_built_from():
    history = (Exchange("kam mara akalet sushi hal shaher?", "SELECT 1"), Exchange("aday?", "CLARIFY: shu?"))
    for names in (NAMES, UserNames([], [], ["Groceries"])):
        for gender in Gender:
            parts = read_prompt(build_prompt("w ekher shaher?", names, TODAY, history, gender=gender))
            assert (parts.question, parts.today, parts.history) == ("w ekher shaher?", TODAY, history)
            assert (list(parts.names.items), list(parts.names.vendors)) == (list(names.items), list(names.vendors))


def test_a_stored_example_gets_the_users_gender_the_new_rule_and_her_reply_form():
    old = old_example(WOMAN, "aday sarafet bi awal el shaher?", "CLARIFY: azdak mn emta la emta?")
    new = rerender(old)
    prompt = new["messages"][0]["content"]
    assert "Today: 2026-12-09 (Wednesday)\nThe user is a woman.\nThe user's items:" in prompt
    assert "In a chat, what the new question says replaces the earlier item" in prompt
    assert new["messages"][1]["content"] == "CLARIFY: azdik mn emta la emta?"
    assert new["labels"]["gender"] == "woman"
    assert without_batch5_lines(prompt) == old["messages"][0]["content"]  # nothing else changed
    assert old["messages"][1]["content"] == "CLARIFY: azdak mn emta la emta?"  # the stored example is not touched


def test_the_neutral_form_goes_to_a_user_whose_gender_is_not_given_and_a_man_keeps_his():
    question, reply = "aya mahal 3am ehke?", "CLARIFY: aya mahal azdak?"
    assert rerender(old_example(NOT_GIVEN, question, reply))["messages"][1]["content"] == "CLARIFY: aya mahal bel zabt?"
    new = rerender(old_example(MAN, question, reply))
    assert new["messages"][1]["content"] == reply and "\nThe user is a man.\n" in new["messages"][0]["content"]


def test_earlier_replies_in_the_chat_take_the_users_form_too():
    history = (Exchange("aday sarafet hal fatra?", "CLARIFY: azdak mn emta la emta?"),)
    new = rerender(old_example(WOMAN, "mn 1 la 5 hal shaher", "SELECT 1", history))
    assert "Question: aday sarafet hal fatra?\nReply: CLARIFY: azdik mn emta la emta?\n" in new["messages"][0]["content"]


def test_rebuilding_twice_gives_the_same_example():
    once = rerender(old_example(WOMAN, "shu?", "CLARIFY: shu baddak ta3ref bel zabt?"))
    assert rerender(once)["messages"][0]["content"] == once["messages"][0]["content"]


@pytest.mark.parametrize("change", [
    lambda p: p.replace("The user's vendors: ", "The user's vendors:  "),
    lambda p: p.replace("Reply:", "Answer:"),
    lambda p: p.replace("\n\nToday:", "\nToday:"),
    lambda p: p.replace("Rules:", "Rule:"),  # different instructions would be silently replaced
])  # fmt: skip
def test_a_prompt_not_in_build_prompts_form_is_refused(change):
    old = old_example(MAN, "aday sarafet?", "SELECT 1")
    old["messages"][0]["content"] = change(old["messages"][0]["content"])
    with pytest.raises(UnreadablePrompt):
        rerender(old)
