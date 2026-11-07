from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.domain.categories.category import (
    MAX_PRIVATE_CATEGORIES,
    RESERVED_NAMES,
    Category,
    clean_name,
    same_name,
)
from app.domain.categories.errors import CategoryAlreadyExists, InvalidCategory


class CategoryService:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def list_all(self, user_id: int) -> list[Category]:
        """Shared defaults plus the user's own categories."""
        with self._uow(user_id) as work:
            return work.categories.list_all()

    def create(self, user_id: int, name: str) -> Category:
        """A new private category. Serialized per user, so two at once cannot both pass the limit; two with the
        same name at once are also stopped by the database's unique index."""
        name = clean_name(name)
        with self._uow(user_id, serialized=True) as work:
            existing = work.categories.list_all()
            if any(same_name(name, taken) for taken in [c.name for c in existing] + list(RESERVED_NAMES)):
                raise CategoryAlreadyExists(f"There is already a category called {name}")
            if sum(not c.is_shared for c in existing) >= MAX_PRIVATE_CATEGORIES:
                raise InvalidCategory(f"You can have at most {MAX_PRIVATE_CATEGORIES} categories of your own")
            return work.categories.add(name)
