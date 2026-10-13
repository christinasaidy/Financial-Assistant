from app.application.receipts.dtos import ReceiptView, to_view
from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.domain.receipts.errors import ReceiptNotFound


class GetReceipt:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, user_id: int, receipt_id: int) -> ReceiptView:
        with self._uow(user_id) as work:
            receipt = work.receipts.get(receipt_id)
        if receipt is None:
            raise ReceiptNotFound
        return to_view(receipt)
