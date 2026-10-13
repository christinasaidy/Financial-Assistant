from app.application.receipts.confirm_receipt import confirm_in
from app.application.receipts.dtos import ConfirmReceiptRequest, ReceiptView, to_view
from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.domain.receipts.status import ReceiptStatus


class CreateManualReceipt:
    """Fully manual entry: a receipt with no file, typed in and confirmed in one step."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, user_id: int, request: ConfirmReceiptRequest) -> ReceiptView:
        with self._uow(user_id) as work:
            receipt_id = work.receipts.create(ReceiptStatus.NEEDS_REVIEW)
            draft = work.receipts.get(receipt_id)
            assert draft is not None
            confirm_in(work, draft, request)
            confirmed = work.receipts.get(receipt_id)
        assert confirmed is not None
        return to_view(confirmed)
