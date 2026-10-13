import pytest

from app.domain.users.errors import InvalidEmail, WeakPassword
from app.domain.users.user import normalize_email, validate_password


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
