"""Finding the user's spelling of a name: only the same spelling is found, anything similar is a suggestion (AC-10)."""

from datetime import date

from app.domain.assistant.names import KnownName, MatchStatus, match_name, spelling_key


def known(*names: str) -> list[KnownName]:
    return [KnownName(name, 1, date(2026, 11, 1)) for name in names]


def test_the_same_spelling_ignoring_case_spaces_and_punctuation_is_found():
    for typed in ("spinneys", "SPINNEYS", " Spinneys ", "spinneys."):
        match = match_name(typed, known("Spinneys", "Carrefour"))
        assert (match.status, [n.name for n in match.names]) == (MatchStatus.FOUND, ["Spinneys"])
    assert match_name("zaatar w zeit", known("Zaatar W Zeit")).status is MatchStatus.FOUND
    assert spelling_key("Pharmacie  Mazen!") == "pharmacie mazen"


def test_a_misspelling_is_only_a_suggestion_never_found():
    match = match_name("spineys", known("Spinneys", "Carrefour"))
    assert match.status is MatchStatus.SUGGESTIONS
    assert [n.name for n in match.names] == ["Spinneys"]


def test_a_shop_and_a_similarly_named_one_are_both_suggested_not_merged():
    """No branch information exists: "Spinneys Achrafieh" may or may not be the same shop as "Spinneys"."""
    match = match_name("spinneys achrafiye", known("Spinneys", "Spinneys Achrafieh"))
    assert match.status is MatchStatus.SUGGESTIONS
    assert {n.name for n in match.names} == {"Spinneys Achrafieh", "Spinneys"}


def test_two_names_with_the_same_spelling_are_ambiguous():
    match = match_name("pharmacie mazen", known("Pharmacie Mazen", "pharmacie mazen"))
    assert match.status is MatchStatus.AMBIGUOUS and len(match.names) == 2


def test_a_name_with_nothing_similar_is_not_found_and_an_empty_one_too():
    assert match_name("zwz", known("Spinneys", "Carrefour")).status is MatchStatus.NOT_FOUND
    assert match_name("  !! ", known("Spinneys")).status is MatchStatus.NOT_FOUND
    assert match_name("milk", []).status is MatchStatus.NOT_FOUND


def test_a_short_name_is_suggested_only_as_a_whole_word():
    assert match_name("tea", known("steak", "team")).status is MatchStatus.NOT_FOUND
    match = match_name("tea", known("steak", "green tea"))
    assert (match.status, [n.name for n in match.names]) == (MatchStatus.SUGGESTIONS, ["green tea"])


def test_at_most_five_suggestions_most_used_first():
    names = [KnownName(f"Spinneys {i}", i, None) for i in range(8)]
    match = match_name("spinneys", names)
    assert match.status is MatchStatus.SUGGESTIONS
    assert [n.receipts for n in match.names] == [7, 6, 5, 4, 3]
