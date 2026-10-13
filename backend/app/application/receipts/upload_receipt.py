from app.application.receipts.dtos import ReceiptView, UploadReceiptRequest, to_view
from app.application.receipts.ports import FileStorage
from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.domain.receipts.errors import DuplicateReceipt
from app.domain.receipts.files import extension_for, file_hash, validate_size
from app.domain.receipts.status import ReceiptStatus


class UploadReceipt:
    """Store an uploaded receipt file. Reading it happens afterwards, in ProcessReceipt."""

    def __init__(self, uow: UnitOfWorkFactory, storage: FileStorage) -> None:
        self._uow = uow
        self._storage = storage

    def execute(self, user_id: int, request: UploadReceiptRequest) -> ReceiptView:
        extension = extension_for(request.content_type)
        validate_size(len(request.content))
        content_hash = file_hash(request.content)

        with self._uow(user_id) as work:
            existing_id = work.receipts.find_id_by_hash(content_hash)
            if existing_id is not None:
                raise DuplicateReceipt(existing_id)

            path = self._storage.save(user_id, request.content, extension)
            try:
                receipt_id = work.receipts.create(ReceiptStatus.UPLOADED, path, content_hash)
                receipt = work.receipts.get(receipt_id)
            except Exception:
                self._storage.delete(path)  # don't leave a file with no receipt
                raise
        assert receipt is not None
        return to_view(receipt)
