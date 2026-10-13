from typing import Protocol

from app.domain.categories.category import Category


class CategoryRepository(Protocol):
    def list_all(self) -> list[Category]:
        """Shared defaults plus the current user's own categories."""
