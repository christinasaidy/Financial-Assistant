import dataclasses
import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.domain.receipts.errors import DuplicateReceipt
from app.domain.receipts.extraction import ExtractedReceipt
from app.domain.receipts.receipt import Receipt, ReceiptLine
from app.domain.receipts.status import ReceiptStatus
from app.domain.shared.currency import Currency

UNIQUE_VIOLATION = "23505"

# A draft has no vendor row yet, so its vendor name comes from the stored extraction. Once confirmed, the
# reviewed vendor is final: a vendor the user cleared stays empty (2026-10-15 code review).
_SELECT_RECEIPT = """
    SELECT r.id, r.status,
           CASE WHEN r.status = 'confirmed' THEN v.name
                ELSE COALESCE(v.name, r.raw_extraction ->> 'vendor_name') END AS vendor_name,
           r.receipt_date, r.currency, r.total, r.primary_category_id, r.file_path, r.created_at,
           r.exchange_rate_used
    FROM receipts r
    LEFT JOIN vendors v ON v.id = r.vendor_id
"""


class SqlReceiptRepository:
    """Works on a connection that is already scoped to one user (see SqlUnitOfWorkFactory).
    Rows are owned by `app_user_id()`, so this class never handles a user id itself."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def create(self, status: ReceiptStatus, file_path: str | None = None, file_hash: str | None = None) -> int:
        try:
            with self._conn.begin_nested():  # a savepoint, so a duplicate doesn't abort the transaction
                return self._conn.execute(
                    text(
                        "INSERT INTO receipts (user_id, status, file_path, file_hash) "
                        "VALUES (app_user_id(), :status, :path, :hash) RETURNING id"
                    ),
                    {"status": status.value, "path": file_path, "hash": file_hash},
                ).scalar_one()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == UNIQUE_VIOLATION and file_hash:
                existing_id = self.find_id_by_hash(file_hash)
                if existing_id is not None:
                    raise DuplicateReceipt(existing_id) from exc
            raise

    def find_id_by_hash(self, file_hash: str) -> int | None:
        return self._conn.execute(
            text("SELECT id FROM receipts WHERE file_hash = :hash"), {"hash": file_hash}
        ).scalar_one_or_none()

    def get(self, receipt_id: int) -> Receipt | None:
        row = self._conn.execute(text(_SELECT_RECEIPT + " WHERE r.id = :id"), {"id": receipt_id}).one_or_none()
        if row is None:
            return None
        return _to_receipt(row, self._lines_by_receipt([receipt_id]).get(receipt_id, ()))

    def list_confirmed_between(self, start: date, end: date) -> list[Receipt]:
        rows = self._conn.execute(
            text(
                _SELECT_RECEIPT
                + " WHERE r.status = 'confirmed' AND r.receipt_date >= :start AND r.receipt_date < :end"
                " ORDER BY r.receipt_date, r.id"
            ),
            {"start": start, "end": end},
        ).all()
        lines = self._lines_by_receipt([row.id for row in rows])
        return [_to_receipt(row, lines.get(row.id, ())) for row in rows]

    def count_with_status(self, status: ReceiptStatus) -> int:
        return self._conn.execute(
            text("SELECT count(*) FROM receipts WHERE status = :status"), {"status": status.value}
        ).scalar_one()

    def existing_ids(self, receipt_ids: Sequence[int]) -> set[int]:
        if not receipt_ids:
            return set()
        rows = self._conn.execute(
            text("SELECT id FROM receipts WHERE id = ANY(:ids)"), {"ids": list(receipt_ids)}
        ).scalars()
        return set(rows)

    def _lines_by_receipt(self, receipt_ids: Sequence[int]) -> dict[int, tuple[ReceiptLine, ...]]:
        """The lines of several receipts in one query, grouped by receipt."""
        if not receipt_ids:
            return {}
        rows = self._conn.execute(
            text(
                "SELECT receipt_id, id, description, line_total, quantity, unit_price, normalized_name, "
                "size_amount, size_unit, category_id FROM receipt_items "
                "WHERE receipt_id = ANY(:ids) ORDER BY receipt_id, id"
            ),
            {"ids": list(receipt_ids)},
        ).all()
        grouped: dict[int, list[ReceiptLine]] = {}
        for line in rows:
            grouped.setdefault(line.receipt_id, []).append(
                ReceiptLine(
                    id=line.id,
                    description=line.description,
                    line_total=line.line_total,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    normalized_name=line.normalized_name,
                    size_amount=line.size_amount,
                    size_unit=line.size_unit,
                    category_id=line.category_id,
                )
            )
        return {receipt_id: tuple(lines) for receipt_id, lines in grouped.items()}

    def list_all(self) -> list[Receipt]:
        rows = self._conn.execute(
            text(_SELECT_RECEIPT + " ORDER BY COALESCE(r.receipt_date, r.created_at::date) DESC, r.id DESC")
        ).all()
        return [_to_receipt(row, ()) for row in rows]

    def set_status(self, receipt_id: int, status: ReceiptStatus) -> None:
        self._conn.execute(
            text("UPDATE receipts SET status = :status, updated_at = now() WHERE id = :id"),
            {"status": status.value, "id": receipt_id},
        )

    def save_extraction(
        self, receipt_id: int, extracted: ExtractedReceipt, vendor_id: int | None, lines: Sequence[ReceiptLine]
    ) -> None:
        self._conn.execute(
            text(
                """
                UPDATE receipts
                SET status = 'needs_review', vendor_id = :vendor_id, receipt_date = :receipt_date,
                    currency = :currency, total = :total, raw_extraction = CAST(:raw AS jsonb), updated_at = now()
                WHERE id = :id
                """
            ),
            {
                "id": receipt_id,
                "vendor_id": vendor_id,
                "receipt_date": extracted.receipt_date,
                "currency": extracted.currency,
                "total": extracted.total,
                "raw": json.dumps(dataclasses.asdict(extracted), default=str),
            },
        )
        self._replace_lines(receipt_id, lines)

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
        self._conn.execute(
            text(
                """
                UPDATE receipts
                SET status = 'confirmed', vendor_id = :vendor_id, receipt_date = :receipt_date,
                    currency = :currency, total = :total, primary_category_id = :category_id,
                    exchange_rate_used = :rate,
                    exchange_rate_source = COALESCE(:rate_source, exchange_rate_source),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {
                "id": receipt_id,
                "vendor_id": vendor_id,
                "receipt_date": receipt_date,
                "currency": currency.value,
                "total": total,
                "category_id": primary_category_id,
                "rate": lbp_per_usd,
                "rate_source": rate_source,
            },
        )
        self._replace_lines(receipt_id, lines)

    def delete(self, receipt_id: int) -> None:
        self._conn.execute(text("DELETE FROM receipts WHERE id = :id"), {"id": receipt_id})

    def category_history(self, normalized_names: Sequence[str]) -> dict[str, list[int]]:
        if not normalized_names:
            return {}
        rows = self._conn.execute(
            text(
                """
                SELECT ri.normalized_name, ri.category_id
                FROM receipt_items ri
                JOIN receipts r ON r.id = ri.receipt_id
                WHERE r.status = 'confirmed' AND ri.category_id IS NOT NULL
                  AND ri.normalized_name = ANY(:names)
                ORDER BY ri.id
                """
            ),
            {"names": list(normalized_names)},
        ).all()
        history: dict[str, list[int]] = {}
        for row in rows:
            history.setdefault(row.normalized_name, []).append(row.category_id)
        return history

    def _replace_lines(self, receipt_id: int, lines: Sequence[ReceiptLine]) -> None:
        self._conn.execute(text("DELETE FROM receipt_items WHERE receipt_id = :id"), {"id": receipt_id})
        if not lines:
            return
        self._conn.execute(
            text(
                """
                INSERT INTO receipt_items (receipt_id, user_id, category_id, description, normalized_name,
                                           size_amount, size_unit, quantity, unit_price, line_total)
                VALUES (:receipt_id, app_user_id(), :category_id, :description, :normalized_name,
                        :size_amount, :size_unit, :quantity, :unit_price, :line_total)
                """
            ),
            [
                {
                    "receipt_id": receipt_id,
                    "category_id": line.category_id,
                    "description": line.description,
                    "normalized_name": line.normalized_name,
                    "size_amount": line.size_amount,
                    "size_unit": line.size_unit,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "line_total": line.line_total,
                }
                for line in lines
            ],
        )


def _to_receipt(row, lines: tuple[ReceiptLine, ...]) -> Receipt:
    return Receipt(
        id=row.id,
        status=ReceiptStatus(row.status),
        vendor_name=row.vendor_name,
        receipt_date=row.receipt_date,
        currency=Currency(row.currency) if row.currency else None,
        total=row.total,
        primary_category_id=row.primary_category_id,
        file_path=row.file_path,
        created_at=row.created_at,
        lines=lines,
        lbp_per_usd=row.exchange_rate_used,
    )
