from dataclasses import replace

from app.application.receipts.dtos import ConfirmReceiptRequest, ReceiptView, to_view
from app.application.shared.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.domain.receipts.errors import InvalidReceipt, ReceiptNotFound
from app.domain.receipts.normalization import normalize_product_name
from app.domain.receipts.receipt import Receipt, validate_confirmation
from app.domain.receipts.status import ReceiptStatus, transition


def confirm_in(work: UnitOfWork, receipt: Receipt, request: ConfirmReceiptRequest) -> None:
    """Apply the user's reviewed values to a receipt, inside the caller's transaction."""
    currency = validate_confirmation(request.currency, request.total, request.lines)

    # Correcting an already confirmed receipt keeps it confirmed. Otherwise the move must be allowed.
    if receipt.status is not ReceiptStatus.CONFIRMED:
        status = receipt.status
        if status is ReceiptStatus.FAILED:  # extraction failed, the user typed the values in
            status = transition(status, ReceiptStatus.NEEDS_REVIEW)
        transition(status, ReceiptStatus.CONFIRMED)

    allowed = {category.id for category in work.categories.list_all()}
    used = {request.primary_category_id, *(line.category_id for line in request.lines)} - {None}
    if not used <= allowed:
        raise InvalidReceipt("Unknown category")

    lines = [
        replace(line, description=line.description.strip(), normalized_name=normalize_product_name(line.normalized_name))
        for line in request.lines
    ]
    vendor_name = (request.vendor_name or "").strip()
    vendor_id = work.vendors.find_or_create(vendor_name) if vendor_name else None
    work.receipts.save_confirmed(
        receipt.id, vendor_id, request.receipt_date, currency, request.total, request.primary_category_id, lines
    )


class ConfirmReceipt:
    """Save the reviewed receipt: vendor, receipt values and lines together, or nothing."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def execute(self, user_id: int, receipt_id: int, request: ConfirmReceiptRequest) -> ReceiptView:
        with self._uow(user_id) as work:
            receipt = work.receipts.get(receipt_id)
            if receipt is None:
                raise ReceiptNotFound
            confirm_in(work, receipt, request)
            confirmed = work.receipts.get(receipt_id)
        assert confirmed is not None
        return to_view(confirmed)
