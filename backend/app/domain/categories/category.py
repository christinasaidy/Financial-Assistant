"""Categories: the shared defaults every user sees, and the user's own private ones.

Rules for a private category's name (decisions approved by the user on 2026-11-07):
- spaces at the ends are trimmed and repeated spaces become one; capitals are kept as typed;
- 1 to 40 characters;
- it must differ, whatever the capitals, from the user's other categories, the shared defaults and the two
  categories the assistant's views make up, so a category filter always names exactly one category;
- at most 50 private categories per user.
"""

from dataclasses import dataclass

from app.domain.assistant.prompt import VIEW_CATEGORIES
from app.domain.categories.errors import InvalidCategory

MAX_NAME_LENGTH = 40
MAX_PRIVATE_CATEGORIES = 50
RESERVED_NAMES = VIEW_CATEGORIES  # made up by the assistant's views, so a user cannot create them


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    is_shared: bool  # a system default visible to every user


def clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise InvalidCategory("The category needs a name")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise InvalidCategory(f"A category name can have at most {MAX_NAME_LENGTH} characters")
    return cleaned


def same_name(first: str, second: str) -> bool:
    return " ".join(first.split()).casefold() == " ".join(second.split()).casefold()
