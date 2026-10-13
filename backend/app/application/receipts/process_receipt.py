from collections.abc import Sequence

from app.application.receipts.ports import FileStorage, ReceiptExtractor
from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.domain.receipts.extraction import ExtractedReceipt, to_draft_lines
from app.domain.receipts.files import content_type_for
from app.domain.receipts.normalization import normalize_product_name
from app.domain.receipts.status import ReceiptStatus, can_transition

MAX_ATTEMPTS = 2  # one retry, then the receipt is marked failed and manual entry is offered


class ProcessReceipt:
    """Read an uploaded receipt with the vision model and save the result as a draft for review."""

    def __init__(self, uow: UnitOfWorkFactory, storage: FileStorage, extractor: ReceiptExtractor) -> None:
        self._uow = uow
        self._storage = storage
        self._extractor = extractor

    def execute(self, user_id: int, receipt_id: int) -> None:
        with self._uow(user_id) as work:
            receipt = work.receipts.get(receipt_id)
            if receipt is None or receipt.file_path is None:
                return
            if not can_transition(receipt.status, ReceiptStatus.PROCESSING):
                return
            work.receipts.set_status(receipt_id, ReceiptStatus.PROCESSING)
            categories = work.categories.list_all()
            file_path = receipt.file_path

        # The model call is slow, so it runs outside any database transaction.
        extracted = self._extract(file_path, [category.name for category in categories])

        with self._uow(user_id) as work:
            if extracted is None:
                work.receipts.set_status(receipt_id, ReceiptStatus.FAILED)
                return
            names = [name for line in extracted.lines if (name := normalize_product_name(line.normalized_name))]
            lines = to_draft_lines(
                extracted,
                category_history=work.receipts.category_history(names),
                category_ids_by_name={category.name.lower(): category.id for category in categories},
            )
            vendor_id = work.vendors.find_by_name(extracted.vendor_name) if extracted.vendor_name else None
            work.receipts.save_extraction(receipt_id, extracted, vendor_id, lines)

    def _extract(self, file_path: str, category_names: Sequence[str]) -> ExtractedReceipt | None:
        # Any failure here must end as status `failed`, never as a receipt stuck in `processing`.
        try:
            content = self._storage.read(file_path)
            content_type = content_type_for(file_path)
        except Exception:
            return None
        for _ in range(MAX_ATTEMPTS):
            try:
                return self._extractor.extract(content, content_type, category_names)
            except Exception:
                continue
        return None
