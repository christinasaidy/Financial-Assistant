from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.domain.categories.category import Category


class CategoryService:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def list_all(self, user_id: int) -> list[Category]:
        """Shared defaults plus the user's own categories."""
        with self._uow(user_id) as work:
            return work.categories.list_all()
