import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.application.notifications.budget_alerts import BudgetAlerts
from app.application.receipts.dtos import ConfirmReceiptRequest, ReceiptView, UploadReceiptRequest, to_view
from app.application.receipts.interfaces import FileStorage, ReceiptExtractor
from app.application.shared.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.domain.notifications.notification import receipt_failed_notification, receipt_ready_notification
from app.domain.receipts.errors import DuplicateReceipt, ExtractionFailed, InvalidReceipt, ReceiptNotFound
from app.domain.receipts.extraction import ExtractedReceipt, rounded_for_storage, to_draft_lines
from app.domain.receipts.files import content_type_for, extension_for, file_hash, validate_size
from app.domain.receipts.normalization import (
    clean_extracted_name,
    name_key,
    names_for_prompt,
    normalize_brand,
    normalize_product_name,
)
from app.domain.receipts.receipt import Receipt, validate_confirmation, validate_draft
from app.domain.receipts.status import ReceiptStatus, can_transition, transition
from app.domain.shared.exchange_rate import validate_rate

logger = logging.getLogger(__name__)

MAX_EXTRACTION_ATTEMPTS = 2  # one retry, then the receipt is marked failed and manual entry is offered
# A stored file younger than this may belong to an upload whose receipt is still being saved.
ORPHAN_MIN_AGE = timedelta(hours=24)
# The statuses a receipt may be claimed for reading from, as the state machine allows (only `uploaded` today).
_CLAIMABLE = tuple(status for status in ReceiptStatus if can_transition(status, ReceiptStatus.PROCESSING))
# How many of the user's item names the model is given to reuse (decision approved 2026-10-16; a judgment that keeps
# the prompt short, not measured). Twice as many are read, because names longer than 3 words are skipped.
KNOWN_NAMES_LIMIT = 200


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
        alerts: BudgetAlerts,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._uow = uow
        self._storage = storage
        self._extractor = extractor
        self._default_lbp_per_usd = default_lbp_per_usd  # saved on receipts confirmed without a rate
        self._alerts = alerts  # budget notifications, checked after anything that changes spending
        self._today = today  # for the future-date review flag

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
                # Raised before the commit, so the transaction rolls back and no receipt points at this file.
                self._remove_file(path)
                raise
        # If the commit itself fails, the file is kept: the receipt may in fact be saved (a connection lost while
        # committing), and deleting its image would lose it. If not, the orphan clean-up finds the file later.
        assert receipt is not None
        return to_view(receipt, self._today())

    def process(self, user_id: int, receipt_id: int) -> None:
        """Read an uploaded receipt with the vision model and save the result as a draft for review."""
        with self._uow(user_id) as work:
            # Checked and claimed in one step, so two calls for the same receipt cannot both read it. The claim
            # is an attempt number: only this attempt may save a result (second code review, finding 10).
            claim = work.receipts.claim_for_processing(receipt_id, _CLAIMABLE)
            if claim is None:
                return
            categories = work.categories.list_all()
            known_names = names_for_prompt(work.receipts.known_item_names(2 * KNOWN_NAMES_LIMIT), KNOWN_NAMES_LIMIT)

        # The model call is slow, so it runs outside any database transaction.
        extracted = self._extract(
            receipt_id, claim.file_path, [category.name for category in categories], known_names
        )
        if extracted is None:
            self._mark_failed(user_id, receipt_id, claim.attempt)
            return

        # From here the receipt is `processing`. Whatever goes wrong, it must end as `failed`
        # so the user can still enter it by hand, never stay stuck.
        try:
            extracted = rounded_for_storage(extracted)
            with self._uow(user_id) as work:
                names = [clean_extracted_name(line.normalized_name) for line in extracted.lines]
                keys = [name_key(name) for name in names if name]
                lines = to_draft_lines(
                    extracted,
                    category_history=work.receipts.category_history(keys),
                    category_ids_by_name={category.name.lower(): category.id for category in categories},
                    known_names=known_names,
                )
                validate_draft(extracted.total, lines)  # e.g. an absurd amount the model invented
                vendor_id = work.vendors.find_by_name(extracted.vendor_name) if extracted.vendor_name else None
                if not work.receipts.save_extraction(receipt_id, claim.attempt, extracted, vendor_id, lines):
                    # Deleted, finished another way, or claimed by a later attempt while the model was reading.
                    logger.info("Receipt %s changed while it was being read; this result was discarded", receipt_id)
                    return
                work.notifications.add(receipt_ready_notification(receipt_id, extracted.vendor_name))
        except Exception:
            logger.exception("Could not save the draft for receipt %s; marking it failed", receipt_id)
            self._mark_failed(user_id, receipt_id, claim.attempt)

    # --- review ---

    def confirm(self, user_id: int, receipt_id: int, request: ConfirmReceiptRequest) -> ReceiptView:
        """Save the reviewed receipt: vendor, receipt values and lines together, or nothing.
        Also used to correct a receipt that is already confirmed."""
        with self._uow(user_id, serialized=True) as work:  # moves budgets: see UnitOfWorkFactory
            receipt = work.receipts.get(receipt_id)
            if receipt is None:
                raise ReceiptNotFound
            self._apply_confirmation(work, receipt, request)
            confirmed = work.receipts.get(receipt_id)
        assert confirmed is not None
        return to_view(confirmed, self._today())

    def create_manual(self, user_id: int, request: ConfirmReceiptRequest) -> ReceiptView:
        """Fully manual entry: a receipt with no file, typed in and confirmed in one step."""
        with self._uow(user_id, serialized=True) as work:  # moves budgets: see UnitOfWorkFactory
            receipt_id = work.receipts.create(ReceiptStatus.NEEDS_REVIEW)
            draft = work.receipts.get(receipt_id)
            assert draft is not None
            self._apply_confirmation(work, draft, request)
            confirmed = work.receipts.get(receipt_id)
        assert confirmed is not None
        return to_view(confirmed, self._today())

    # --- reading and deleting ---

    def get(self, user_id: int, receipt_id: int) -> ReceiptView:
        with self._uow(user_id) as work:
            receipt = work.receipts.get(receipt_id)
        if receipt is None:
            raise ReceiptNotFound
        return to_view(receipt, self._today())

    def list_all(self, user_id: int) -> list[Receipt]:
        """The user's receipts, newest first, without their lines."""
        with self._uow(user_id) as work:
            return work.receipts.list_all()

    def delete(self, user_id: int, receipt_id: int) -> None:
        with self._uow(user_id, serialized=True) as work:  # moves budgets: see UnitOfWorkFactory
            receipt = work.receipts.get(receipt_id)
            if receipt is None:
                raise ReceiptNotFound
            work.receipts.delete(receipt_id)
            self._alerts.check(work)
        # Only after the row is really gone, so a failed delete never loses the image. The receipt is deleted
        # either way; a file that cannot be removed now is left for the orphan clean-up, not reported as an error.
        if receipt.file_path:
            self._remove_file(receipt.file_path)

    # --- files no receipt points at ---

    def find_orphaned_files(self) -> dict[int, list[str]]:
        """Stored files that no receipt points at, by user: left by an upload whose save failed, a file that could
        not be removed when its receipt was deleted, or a half-written file. Only files older than ORPHAN_MIN_AGE
        count, so an upload still being saved is never one. A committed receipt always points at its file, so a
        valid receipt's image is never listed (second code review, finding 11)."""
        cutoff = datetime.now(UTC) - ORPHAN_MIN_AGE
        orphans: dict[int, list[str]] = {}
        for user_id in self._storage.user_ids():
            old_files = [file.path for file in self._storage.list_files(user_id) if file.modified_at <= cutoff]
            if not old_files:
                continue
            with self._uow(user_id) as work:  # as that user, so row-level security shows exactly their receipts
                referenced = work.receipts.file_paths()
            if found := [path for path in old_files if path not in referenced]:
                orphans[user_id] = found
        return orphans

    def remove_orphaned_files(self) -> dict[int, list[str]]:
        """Remove what `find_orphaned_files` finds. Safe to run at any time: a file is never given to a new receipt
        once stored (every upload gets a new random name). Returns what was actually removed."""
        removed: dict[int, list[str]] = {}
        for user_id, paths in self.find_orphaned_files().items():
            if done := [path for path in paths if self._remove_file(path)]:
                removed[user_id] = done
        return removed

    # --- helpers ---

    def _apply_confirmation(self, work: UnitOfWork, receipt: Receipt, request: ConfirmReceiptRequest) -> None:
        """Apply the user's reviewed values to a receipt, inside the caller's transaction."""
        currency = validate_confirmation(request.currency, request.total, request.lines, request.vendor_name)

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
                normalized_name=normalize_product_name(line.normalized_name),  # kept as typed, only tidied
                brand=normalize_brand(line.brand),
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
        self._alerts.check(work)  # covers confirming, correcting and manual entry

    def _remove_file(self, path: str) -> bool:
        try:
            self._storage.delete(path)
            return True
        except Exception:
            logger.exception("Could not remove the receipt file %s; it is left for the orphan clean-up", path)
            return False

    def _mark_failed(self, user_id: int, receipt_id: int, attempt: int) -> None:
        with self._uow(user_id) as work:
            if not work.receipts.fail_processing(receipt_id, attempt):
                return  # no longer this attempt's receipt: never mark a confirmed or deleted receipt failed
            receipt = work.receipts.get(receipt_id)
            assert receipt is not None
            work.notifications.add(receipt_failed_notification(receipt_id, receipt.created_at.date()))

    def _extract(
        self, receipt_id: int, file_path: str, category_names: Sequence[str], known_names: Sequence[str]
    ) -> ExtractedReceipt | None:
        # Any failure here must end as status `failed`, never as a receipt stuck in `processing`.
        try:
            content = self._storage.read(file_path)
            content_type = content_type_for(file_path)
        except Exception:
            logger.exception("Could not read the stored file for receipt %s", receipt_id)
            return None
        for attempt in range(1, MAX_EXTRACTION_ATTEMPTS + 1):
            try:
                return self._extractor.extract(content, content_type, category_names, known_names)
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
