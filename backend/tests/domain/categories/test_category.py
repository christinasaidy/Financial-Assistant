"""Private category names (decisions approved by the user on 2026-11-07). Do not change an expected value to make a
test pass."""

import pytest

from app.domain.categories.category import MAX_NAME_LENGTH, clean_name, same_name
from app.domain.categories.errors import InvalidCategory


def test_spaces_are_trimmed_and_collapsed_and_capitals_kept():
    assert clean_name("  Home   Office ") == "Home Office"
    assert clean_name("Pets") == "Pets"


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_a_blank_name_is_refused(name):
    with pytest.raises(InvalidCategory):
        clean_name(name)


def test_names_up_to_40_characters_are_accepted():
    assert MAX_NAME_LENGTH == 40
    assert clean_name("x" * 40) == "x" * 40
    with pytest.raises(InvalidCategory):
        clean_name("x" * 41)


def test_names_are_the_same_whatever_the_capitals_and_spacing():
    assert same_name("pets", "Pets")
    assert same_name(" Home  office", "Home Office")
    assert not same_name("Pet", "Pets")
