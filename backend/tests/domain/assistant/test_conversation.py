import pytest

from app.domain.assistant.conversation import MAX_QUESTION_LENGTH, Rating, clean_question, title_from
from app.domain.assistant.errors import InvalidQuestion


def test_a_short_question_is_its_own_title():
    assert title_from("How much did I spend on groceries this month?") == (
        "How much did I spend on groceries this month?"
    )


def test_a_long_question_is_cut_to_60_characters_with_an_ellipsis():
    question = "Adde sarafet 3al akel w 3al supermarket w 3al benzine l jem3a l madye w hal jem3a kamen?"
    title = title_from(question)
    assert len(title) == 60
    assert title.endswith("…")
    assert question.startswith(title[:-1])


def test_spaces_are_tidied():
    assert clean_question("  how   much\nthis month ") == "how much this month"


@pytest.mark.parametrize("bad", ["", "   ", "\n", "x" * (MAX_QUESTION_LENGTH + 1)])
def test_empty_or_huge_questions_are_refused(bad):
    with pytest.raises(InvalidQuestion):
        clean_question(bad)


def test_ratings_are_stored_as_plus_or_minus_one():
    assert (Rating.UP.score, Rating.DOWN.score) == (1, -1)
    assert (Rating.from_score(1), Rating.from_score(-1)) == (Rating.UP, Rating.DOWN)
