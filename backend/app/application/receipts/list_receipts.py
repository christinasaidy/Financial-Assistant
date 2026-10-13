from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.domain.receipts.receipt import Receipt


class ListReceipts:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, user_id: int) -> list[Receipt]:
        with self._uow(user_id) as work:
            return work.receipts.list_all()
