import pytest

from app.domain.users.errors import InvalidEmail, InvalidFirstName, InvalidGender, WeakPassword
from app.domain.users.user import Gender, normalize_email, normalize_first_name, parse_gender, validate_password


def test_email_is_trimmed_and_lowercased():
    assert normalize_email("  Christina@Example.COM ") == "christina@example.com"


@pytest.mark.parametrize("bad", ["", "no-at-sign", "a@b", "a b@c.com", "@c.com", "a@@c.com", "a@" + "b" * 260 + ".com"])
def test_invalid_emails_are_rejected(bad):
    with pytest.raises(InvalidEmail):
        normalize_email(bad)


def test_password_length_limits():
    validate_password("x" * 8)
    validate_password("x" * 128)
    with pytest.raises(WeakPassword):
        validate_password("x" * 7)
    with pytest.raises(WeakPassword):
        validate_password("x" * 129)


def test_first_name_is_trimmed_and_keeps_its_case():
    assert normalize_first_name("  Christina ") == "Christina"
    assert normalize_first_name("Jean-Marc") == "Jean-Marc"
    assert normalize_first_name("\u0631\u064a\u0645\u0627") == "\u0631\u064a\u0645\u0627"  # Arabic is fine


def test_first_name_length_limits_count_after_trimming():
    assert normalize_first_name("x") == "x"
    assert normalize_first_name("x" * 50) == "x" * 50
    assert normalize_first_name("  " + "x" * 50 + "  ") == "x" * 50
    with pytest.raises(InvalidFirstName, match="at most 50"):
        normalize_first_name("x" * 51)


@pytest.mark.parametrize("bad", ["", " ", "\t\n ", "Chris\x00tina"])
def test_blank_or_unstorable_first_names_are_rejected(bad):
    with pytest.raises(InvalidFirstName):
        normalize_first_name(bad)


def test_the_three_genders_are_accepted():
    assert parse_gender("female") is Gender.FEMALE
    assert parse_gender("male") is Gender.MALE
    assert parse_gender("prefer_not_to_say") is Gender.PREFER_NOT_TO_SAY


@pytest.mark.parametrize("bad", ["", "Female", "FEMALE", " female", "other", "f", "prefer not to say"])
def test_any_other_gender_is_rejected(bad):
    with pytest.raises(InvalidGender):
        parse_gender(bad)
