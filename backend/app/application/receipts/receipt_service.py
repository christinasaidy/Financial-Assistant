import logging
from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal

from app.application.receipts.dtos import ConfirmReceiptRequest, ReceiptView, UploadReceiptRequest, to_view
from app.application.receipts.interfaces import FileStorage, ReceiptExtractor
from app.application.shared.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.domain.receipts.errors import DuplicateReceipt, ExtractionFailed, InvalidReceipt, ReceiptNotFound
from app.domain.receipts.extraction import ExtractedReceipt, to_draft_lines
from app.domain.receipts.files import content_type_for, extension_for, file_hash, validate_size
from app.domain.receipts.normalization import normalize_product_name
from app.domain.receipts.receipt import Receipt, validate_confirmation, validate_draft
from app.domain.receipts.status import ReceiptStatus, can_transition, transition
from app.domain.shared.exchange_rate import validate_rate

logger = logging.getLogger(__name__)

MAX_EXTRACTION_ATTEMPTS = 2  # one retry, then the receipt is marked failed and manual entry is offered


class ReceiptService:
    """The receipt flow: upload -> read with the vision model -> review -> confirm.

    Every method that touches user data opens one unit of work, so its changes are saved
    together or not at all, and always as the given user.
    """

    def __init__(
        self,
        uow: UnitOfWorkFactory,
        storage: FileStorage,
        extractor: ReceiptExtractor,
        default_lbp_per_usd: Decimal,
    ) -> None:
        self._uow = uow
        self._storage = storage
        self._extractor = extractor
        self._default_lbp_per_usd = default_lbp_per_usd  # saved on receipts confirmed without a rate

    # --- upload and background reading ---

    def upload(self, user_id: int, request: UploadReceiptRequest) -> ReceiptView:
        """Store an uploaded receipt file. Reading it happens afterwards, in `process`."""
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

    def process(self, user_id: int, receipt_id: int) -> None:
        """Read an uploaded receipt with the vision model and save the result as a draft for review."""
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
        extracted = self._extract(receipt_id, file_path, [category.name for category in categories])
        if extracted is None:
            self._mark_failed(user_id, receipt_id)
            return

        # From here the receipt is `processing`. Whatever goes wrong, it must end as `failed`
        # so the user can still enter it by hand, never stay stuck.
        try:
            with self._uow(user_id) as work:
                names = [name for line in extracted.lines if (name := normalize_product_name(line.normalized_name))]
                lines = to_draft_lines(
                    extracted,
                    category_history=work.receipts.category_history(names),
                    category_ids_by_name={category.name.lower(): category.id for category in categories},
                )
                validate_draft(extracted.total, lines)  # e.g. an absurd amount the model invented
                vendor_id = work.vendors.find_by_name(extracted.vendor_name) if extracted.vendor_name else None
                work.receipts.save_extraction(receipt_id, extracted, vendor_id, lines)
        except Exception:
            logger.exception("Could not save the draft for receipt %s; marking it failed", receipt_id)
            self._mark_failed(user_id, receipt_id)

    # --- review ---

    def confirm(self, user_id: int, receipt_id: int, request: ConfirmReceiptRequest) -> ReceiptView:
        """Save the reviewed receipt: vendor, receipt values and lines together, or nothing.
        Also used to correct a receipt that is already confirmed."""
        with self._uow(user_id) as work:
            receipt = work.receipts.get(receipt_id)
            if receipt is None:
                raise ReceiptNotFound
            self._apply_confirmation(work, receipt, request)
            confirmed = work.receipts.get(receipt_id)
        assert confirmed is not None
        return to_view(confirmed)

    def create_manual(self, user_id: int, request: ConfirmReceiptRequest) -> ReceiptView:
        """Fully manual entry: a receipt with no file, typed in and confirmed in one step."""
        with self._uow(user_id) as work:
            receipt_id = work.receipts.create(ReceiptStatus.NEEDS_REVIEW)
            draft = work.receipts.get(receipt_id)
            assert draft is not None
            self._apply_confirmation(work, draft, request)
            confirmed = work.receipts.get(receipt_id)
        assert confirmed is not None
        return to_view(confirmed)

    # --- reading and deleting ---

    def get(self, user_id: int, receipt_id: int) -> ReceiptView:
        with self._uow(user_id) as work:
            receipt = work.receipts.get(receipt_id)
        if receipt is None:
            raise ReceiptNotFound
        return to_view(receipt)

    def list_all(self, user_id: int) -> list[Receipt]:
        """The user's receipts, newest first, without their lines."""
        with self._uow(user_id) as work:
            return work.receipts.list_all()

    def delete(self, user_id: int, receipt_id: int) -> None:
        with self._uow(user_id) as work:
            receipt = work.receipts.get(receipt_id)
            if receipt is None:
                raise ReceiptNotFound
            work.receipts.delete(receipt_id)
        # Only after the row is really gone, so a failed delete never loses the image.
        if receipt.file_path:
            self._storage.delete(receipt.file_path)

    # --- helpers ---

    def _apply_confirmation(self, work: UnitOfWork, receipt: Receipt, request: ConfirmReceiptRequest) -> None:
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
            replace(
                line,
                description=line.description.strip(),
                normalized_name=normalize_product_name(line.normalized_name),
            )
            for line in request.lines
        ]
        # The rate is saved on the receipt so it is always converted at the rate of its own time.
        if request.lbp_per_usd is not None:
            rate, rate_source = request.lbp_per_usd, "user"
        elif receipt.lbp_per_usd is not None:  # a correction keeps the rate saved the first time
            rate, rate_source = receipt.lbp_per_usd, None
        else:
            rate, rate_source = self._default_lbp_per_usd, "default"
        validate_rate(rate)

        vendor_name = (request.vendor_name or "").strip()
        vendor_id = work.vendors.find_or_create(vendor_name) if vendor_name else None
        work.receipts.save_confirmed(
            receipt.id,
            vendor_id,
            request.receipt_date,
            currency,
            request.total,
            request.primary_category_id,
            lines,
            rate,
            rate_source,
        )

    def _mark_failed(self, user_id: int, receipt_id: int) -> None:
        with self._uow(user_id) as work:
            work.receipts.set_status(receipt_id, ReceiptStatus.FAILED)

    def _extract(self, receipt_id: int, file_path: str, category_names: Sequence[str]) -> ExtractedReceipt | None:
        # Any failure here must end as status `failed`, never as a receipt stuck in `processing`.
        try:
            content = self._storage.read(file_path)
            content_type = content_type_for(file_path)
        except Exception:
            logger.exception("Could not read the stored file for receipt %s", receipt_id)
            return None
        for attempt in range(1, MAX_EXTRACTION_ATTEMPTS + 1):
            try:
                return self._extractor.extract(content, content_type, category_names)
            except Exception as exc:
                # An ExtractionFailed already says what went wrong; anything else is a bug worth a traceback.
                logger.warning(
                    "Extraction attempt %s of %s failed for receipt %s: %s",
                    attempt,
                    MAX_EXTRACTION_ATTEMPTS,
                    receipt_id,
                    exc,
                    exc_info=not isinstance(exc, ExtractionFailed),
                )
        return None
