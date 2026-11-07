from typing import Protocol

from app.domain.categories.category import Category


class CategoryRepository(Protocol):
    def list_all(self) -> list[Category]:
        """Shared defaults plus the current user's own categories."""

    def add(self, name: str) -> Category:
        """Create a private category for the current user. Raises CategoryAlreadyExists if the user already has
        one with this name (whatever the capitals)."""
