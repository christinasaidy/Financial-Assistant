from app.application.receipts.ports import FileStorage
from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.domain.receipts.errors import ReceiptNotFound


class DeleteReceipt:
    def __init__(self, uow: UnitOfWorkFactory, storage: FileStorage) -> None:
        self._uow = uow
        self._storage = storage

    def execute(self, user_id: int, receipt_id: int) -> None:
        with self._uow(user_id) as work:
            receipt = work.receipts.get(receipt_id)
            if receipt is None:
                raise ReceiptNotFound
            work.receipts.delete(receipt_id)
        # Only after the row is really gone, so a failed delete never loses the image.
        if receipt.file_path:
            self._storage.delete(receipt.file_path)
