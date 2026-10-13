from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.domain.categories.category import Category


class ListCategories:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, user_id: int) -> list[Category]:
        with self._uow(user_id) as work:
            return work.categories.list_all()
