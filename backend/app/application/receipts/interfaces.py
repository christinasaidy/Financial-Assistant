from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from app.domain.receipts.extraction import ExtractedReceipt
from app.domain.receipts.receipt import Receipt, ReceiptLine
from app.domain.receipts.status import ReceiptStatus
from app.domain.shared.currency import Currency


@dataclass(frozen=True)
class ProcessingClaim:
    """Proof that this worker owns the current attempt at reading a receipt."""

    attempt: int
    file_path: str


class ReceiptRepository(Protocol):
    def create(self, status: ReceiptStatus, file_path: str | None = None, file_hash: str | None = None) -> int:
        """Raises DuplicateReceipt if this user already has a receipt with the same file hash."""

    def find_id_by_hash(self, file_hash: str) -> int | None: ...

    def get(self, receipt_id: int) -> Receipt | None:
        """The receipt with its lines, or None if it does not exist for this user."""

    def list_all(self) -> list[Receipt]:
        """All of the user's receipts, newest first, without their lines."""

    def claim_for_processing(self, receipt_id: int, from_statuses: Sequence[ReceiptStatus]) -> ProcessingClaim | None:
        """Atomically move the receipt to processing if it has a file and is in one of `from_statuses`, starting
        a new attempt. None if it is not (another worker claimed it first, or it was deleted)."""

    def save_extraction(
        self,
        receipt_id: int,
        attempt: int,
        extracted: ExtractedReceipt,
        vendor_id: int | None,
        lines: Sequence[ReceiptLine],
    ) -> bool:
        """Store the model's output as a draft and move the receipt to needs_review, only if it is still processing
        under this attempt. False (and nothing written) if not: it was deleted, finished another way, or claimed
        again by a later attempt."""

    def fail_processing(self, receipt_id: int, attempt: int) -> bool:
        """Move the receipt to failed, under the same condition as save_extraction."""

    def save_confirmed(
        self,
        receipt_id: int,
        vendor_id: int | None,
        receipt_date: date,
        currency: Currency,
        total: Decimal,
        primary_category_id: int | None,
        lines: Sequence[ReceiptLine],
        lbp_per_usd: Decimal,
        rate_source: str | None,
    ) -> None:
        """Replace the receipt's values and lines with the confirmed ones.
        `rate_source` is "user" or "default"; None keeps the source already saved."""

    def delete(self, receipt_id: int) -> None: ...

    def list_confirmed_between(self, start: date, end: date) -> list[Receipt]:
        """Confirmed receipts dated from `start` up to but not including `end`, with their lines."""

    def count_with_status(self, status: ReceiptStatus) -> int: ...

    def existing_ids(self, receipt_ids: Sequence[int]) -> set[int]:
        """Which of these receipts still exist for this user."""

    def file_paths(self) -> set[str]:
        """The stored-file paths of all of the user's receipts."""

    def category_history(self, name_keys: Sequence[str]) -> dict[str, list[int]]:
        """For each name key (see `normalization.name_key`: the same words in any order), the categories the user
        confirmed for lines with that key before, oldest first."""

    def known_item_names(self, limit: int) -> list[str]:
        """The user's distinct item names on confirmed receipts, most recently used first, at most `limit`."""


class VendorRepository(Protocol):
    def find_by_name(self, name: str) -> int | None: ...

    def find_or_create(self, name: str) -> int: ...


@dataclass(frozen=True)
class StoredFile:
    path: str  # as kept in the database
    modified_at: datetime  # timezone-aware


class FileStorage(Protocol):
    def save(self, user_id: int, content: bytes, extension: str) -> str:
        """Store the file and return the path to keep in the database."""

    def read(self, path: str) -> bytes: ...

    def delete(self, path: str) -> None: ...

    def user_ids(self) -> list[int]:
        """The users that have stored files."""

    def list_files(self, user_id: int) -> list[StoredFile]:
        """The files this storage saved for the user, including any left half-written. Nothing else: a file it
        did not name itself is never listed, so it can never be cleaned up by mistake."""


class ReceiptExtractor(Protocol):
    def extract(
        self, content: bytes, content_type: str, category_names: Sequence[str], known_names: Sequence[str] = ()
    ) -> ExtractedReceipt:
        """Read a receipt image or PDF. Raises ExtractionFailed if the output is unusable. `known_names` are the
        user's item names, most recently used first, which the model should reuse for the same product."""
