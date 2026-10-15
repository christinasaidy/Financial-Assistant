from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.domain.receipts.extraction import ExtractedReceipt
from app.domain.receipts.receipt import Receipt, ReceiptLine
from app.domain.receipts.status import ReceiptStatus
from app.domain.shared.currency import Currency


class ReceiptRepository(Protocol):
    def create(self, status: ReceiptStatus, file_path: str | None = None, file_hash: str | None = None) -> int:
        """Raises DuplicateReceipt if this user already has a receipt with the same file hash."""

    def find_id_by_hash(self, file_hash: str) -> int | None: ...

    def get(self, receipt_id: int) -> Receipt | None:
        """The receipt with its lines, or None if it does not exist for this user."""

    def list_all(self) -> list[Receipt]:
        """All of the user's receipts, newest first, without their lines."""

    def set_status(self, receipt_id: int, status: ReceiptStatus) -> None: ...

    def save_extraction(
        self, receipt_id: int, extracted: ExtractedReceipt, vendor_id: int | None, lines: Sequence[ReceiptLine]
    ) -> None:
        """Store the model's output as a draft and move the receipt to needs_review."""

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

    def category_history(self, normalized_names: Sequence[str]) -> dict[str, list[int]]:
        """For each name, the categories the user confirmed for it before, oldest first."""


class VendorRepository(Protocol):
    def find_by_name(self, name: str) -> int | None: ...

    def find_or_create(self, name: str) -> int: ...


class FileStorage(Protocol):
    def save(self, user_id: int, content: bytes, extension: str) -> str:
        """Store the file and return the path to keep in the database."""

    def read(self, path: str) -> bytes: ...

    def delete(self, path: str) -> None: ...


class ReceiptExtractor(Protocol):
    def extract(self, content: bytes, content_type: str, category_names: Sequence[str]) -> ExtractedReceipt:
        """Read a receipt image or PDF. Raises ExtractionFailed if the output is unusable."""
