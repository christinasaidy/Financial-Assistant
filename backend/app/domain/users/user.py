import re
from dataclasses import dataclass
from enum import StrEnum

from app.domain.users.errors import InvalidEmail, InvalidFirstName, InvalidGender, WeakPassword

MAX_EMAIL_LENGTH = 254
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128  # bounds the work a single request can force the hasher to do
MAX_FIRST_NAME_LENGTH = 50

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Gender(StrEnum):
    FEMALE = "female"
    MALE = "male"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


@dataclass(frozen=True)
class User:
    id: int
    email: str
    # Asked at registration. Accounts made before that have neither, so both may be None.
    first_name: str | None
    gender: Gender | None


def normalize_email(raw: str) -> str:
    """Trim and lower-case an email so the same address is always stored one way."""
    email = raw.strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or not _EMAIL_PATTERN.match(email):
        raise InvalidEmail("Enter a valid email address")
    return email


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPassword(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")


def normalize_first_name(raw: str) -> str:
    """Trim the name; it must then be 1 to 50 characters. The case is kept as typed."""
    first_name = raw.strip()
    if not first_name:
        raise InvalidFirstName("Enter your first name")
    if len(first_name) > MAX_FIRST_NAME_LENGTH:
        raise InvalidFirstName(f"First name must be at most {MAX_FIRST_NAME_LENGTH} characters")
    if "\x00" in first_name:  # PostgreSQL text cannot hold NUL
        raise InvalidFirstName("First name contains a character that cannot be saved (NUL)")
    return first_name


def parse_gender(raw: str) -> Gender:
    try:
        return Gender(raw)
    except ValueError:
        raise InvalidGender("Gender must be female, male or prefer_not_to_say") from None
