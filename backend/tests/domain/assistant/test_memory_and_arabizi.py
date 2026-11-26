"""What may be remembered, and the Arabizi checks on an answer."""

import pytest

from app.domain.assistant.arabizi import Address, ArabiziWords, address_for, problems
from app.domain.assistant.errors import InvalidMemory
from app.domain.assistant.memory import MAX_TEXT_LENGTH, alias_text, clean_alias, clean_text
from app.domain.assistant.names import NameKind
from app.domain.users.user import Gender

WORDS = ArabiziWords(frozenset({"sakin", "li fet"}), frozenset({"sarafet", "baddak"}), frozenset({"sarafte"}))


def test_a_preference_is_cleaned_and_bounded():
    assert clean_text("  Keep   your answers short ") == "Keep your answers short"
    with pytest.raises(InvalidMemory):
        clean_text("   ")
    with pytest.raises(InvalidMemory):
        clean_text("x" * (MAX_TEXT_LENGTH + 1))


@pytest.mark.parametrize("text", ["I spent $250 this month", "My rent is 500 USD", "Budget 300,000 LBP",
                                  "I owe 50 dollars", "1m lira on groceries"])  # fmt: skip
def test_amounts_are_never_remembered(text):
    with pytest.raises(InvalidMemory, match="Amounts are not remembered"):
        clean_text(text)


def test_numbers_that_are_not_amounts_can_be_remembered():
    assert clean_text("Show me the top 3 shops") == "Show me the top 3 shops"


def test_an_alias_reads_as_a_sentence():
    assert clean_alias(" zwz ") == "zwz"
    assert alias_text("zwz", NameKind.VENDOR, "Zaatar w Zeit") == '"zwz" means the shop "Zaatar w Zeit"'
    with pytest.raises(InvalidMemory):
        clean_alias("x" * 61)


def test_the_reply_forms_follow_the_gender_chosen_at_sign_up():
    assert address_for(Gender.MALE) is Address.MAN
    assert address_for(Gender.FEMALE) is Address.WOMAN
    assert address_for(Gender.PREFER_NOT_TO_SAY) is Address.NEUTRAL
    assert address_for(None) is Address.NEUTRAL  # accounts from before gender was asked


def test_a_rejected_spelling_is_found_as_a_whole_word_in_any_case():
    assert problems("Sakin, ma fi shi", WORDS, Address.MAN) == ["rejected spelling sakin"]
    assert problems("el shaher li fet", WORDS, Address.MAN) == ["rejected spelling li fet"]
    assert problems("sakinet", WORDS, Address.MAN) == []  # part of another word is not the word


def test_words_of_the_other_gender_and_gendered_words_for_neutral():
    assert problems("sarafet $5", WORDS, Address.MAN) == []
    assert problems("sarafet $5", WORDS, Address.WOMAN) == ["words not for a woman reader: sarafet"]
    assert problems("sarafte $5", WORDS, Address.MAN) == ["words not for a man reader: sarafte"]
    assert problems("sarafte $5", WORDS, Address.NEUTRAL) == ["gendered words, but the user's gender is not given: "
                                                               "sarafte"]  # fmt: skip


def test_the_users_own_words_and_the_datas_names_are_allowed():
    assert problems("Your shop Sakin", WORDS, Address.NEUTRAL, ['{"vendor": "Sakin"}']) == []
    assert problems("sarafet?", WORDS, Address.NEUTRAL, ["kam sarafet?"]) == []
