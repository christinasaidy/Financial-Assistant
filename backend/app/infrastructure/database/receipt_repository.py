import dataclasses
import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import Connection, Row, text
from sqlalchemy.exc import IntegrityError

from app.application.receipts.interfaces import ProcessingClaim
from app.domain.receipts.errors import DuplicateReceipt
from app.domain.receipts.extraction import ExtractedReceipt
from app.domain.receipts.receipt import Receipt, ReceiptLine
from app.domain.receipts.status import ReceiptStatus
from app.domain.shared.currency import Currency

UNIQUE_VIOLATION = "23505"

# A draft has no vendor row yet, so its vendor name comes from the stored extraction. Once confirmed, the
# reviewed vendor is final: a vendor the user cleared stays empty (2026-10-15 code review).
_RECEIPT_COLUMNS = """
    r.id, r.status,
    CASE WHEN r.status = 'confirmed' THEN v.name
         ELSE COALESCE(v.name, r.raw_extraction ->> 'vendor_name') END AS vendor_name,
    r.receipt_date, r.currency, r.total, r.primary_category_id, r.file_path, r.created_at, r.exchange_rate_used
"""
_LINE_COLUMNS = """
    li.id AS line_id, li.description AS line_description, li.line_total, li.quantity AS line_quantity,
    li.unit_price AS line_unit_price, li.normalized_name AS line_normalized_name,
    li.size_amount AS line_size_amount, li.size_unit AS line_size_unit, li.category_id AS line_category_id,
    li.brand AS line_brand
"""
# A line's name key in SQL, the same as `normalization.name_key`: its words sorted, joined by one space. Stored
# names are already lower case with single spaces. COLLATE "C" sorts by code point, as Python's sorted() does
# (the dev database's own English collation would put "éclair" before "fig"; Python puts it after).
_NAME_KEY = (
    "array_to_string(ARRAY(SELECT word FROM unnest(string_to_array(ri.normalized_name, ' ')) AS word "
    "ORDER BY word COLLATE \"C\"), ' ')"
)
_SELECT_RECEIPT = f"SELECT {_RECEIPT_COLUMNS} FROM receipts r LEFT JOIN vendors v ON v.id = r.vendor_id"
# Each receipt once per line, or once with NULL line columns if it has no lines. See `_with_lines`.
_SELECT_RECEIPT_WITH_LINES = (
    f"SELECT {_RECEIPT_COLUMNS}, {_LINE_COLUMNS} FROM receipts r LEFT JOIN vendors v ON v.id = r.vendor_id"
    " LEFT JOIN receipt_items li ON li.receipt_id = r.id"
)


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
        receipts = self._with_lines("r.id = :id", "r.id", {"id": receipt_id})
        return receipts[0] if receipts else None

    def list_confirmed_between(self, start: date, end: date) -> list[Receipt]:
        return self._with_lines(
            "r.status = 'confirmed' AND r.receipt_date >= :start AND r.receipt_date < :end",
            "r.receipt_date, r.id",
            {"start": start, "end": end},
        )

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

    def _with_lines(self, where: str, order_by: str, params: dict) -> list[Receipt]:
        """Receipts with their lines, read in ONE statement. A statement sees a single snapshot of the database, so
        a receipt corrected or deleted meanwhile is seen wholly before or wholly after the change; reading headers
        and lines in two statements could combine an old total with new lines (second code review, finding 9)."""
        rows = self._conn.execute(
            text(f"{_SELECT_RECEIPT_WITH_LINES} WHERE {where} ORDER BY {order_by}, li.id"), params
        ).all()
        receipts: dict[int, tuple[Row, list[ReceiptLine]]] = {}  # in query order
        for row in rows:
            _, lines = receipts.setdefault(row.id, (row, []))
            if row.line_id is not None:  # a receipt without lines still comes back once, with NULL line columns
                lines.append(
                    ReceiptLine(
                        id=row.line_id,
                        description=row.line_description,
                        line_total=row.line_total,
                        quantity=row.line_quantity,
                        unit_price=row.line_unit_price,
                        normalized_name=row.line_normalized_name,
                        size_amount=row.line_size_amount,
                        size_unit=row.line_size_unit,
                        category_id=row.line_category_id,
                        brand=row.line_brand,
                    )
                )
        return [_to_receipt(row, tuple(lines)) for row, lines in receipts.values()]

    def list_all(self) -> list[Receipt]:
        rows = self._conn.execute(
            text(_SELECT_RECEIPT + " ORDER BY COALESCE(r.receipt_date, r.created_at::date) DESC, r.id DESC")
        ).all()
        return [_to_receipt(row, ()) for row in rows]

    def claim_for_processing(self, receipt_id: int, from_statuses: Sequence[ReceiptStatus]) -> ProcessingClaim | None:
        # One UPDATE checks and claims together. A second worker's UPDATE waits on the row lock, then re-checks the
        # status of the committed row (READ COMMITTED), finds it already processing, and claims nothing.
        row = self._conn.execute(
            text(
                """
                UPDATE receipts
                SET status = 'processing', processing_attempt = processing_attempt + 1, updated_at = now()
                WHERE id = :id AND status = ANY(:from_statuses) AND file_path IS NOT NULL
                RETURNING processing_attempt, file_path
                """
            ),
            {"id": receipt_id, "from_statuses": [status.value for status in from_statuses]},
        ).one_or_none()
        return ProcessingClaim(row.processing_attempt, row.file_path) if row else None

    def save_extraction(
        self,
        receipt_id: int,
        attempt: int,
        extracted: ExtractedReceipt,
        vendor_id: int | None,
        lines: Sequence[ReceiptLine],
    ) -> bool:
        saved = self._conn.execute(
            text(
                """
                UPDATE receipts
                SET status = 'needs_review', vendor_id = :vendor_id, receipt_date = :receipt_date,
                    currency = :currency, total = :total, raw_extraction = CAST(:raw AS jsonb), updated_at = now()
                WHERE id = :id AND status = 'processing' AND processing_attempt = :attempt
                """
            ),
            {
                "id": receipt_id,
                "attempt": attempt,
                "vendor_id": vendor_id,
                "receipt_date": extracted.receipt_date,
                "currency": extracted.currency,
                "total": extracted.total,
                "raw": json.dumps(dataclasses.asdict(extracted), default=str),
            },
        ).rowcount
        if not saved:
            return False  # not this attempt's receipt any more: its lines are left alone too
        self._replace_lines(receipt_id, lines)
        return True

    def fail_processing(self, receipt_id: int, attempt: int) -> bool:
        return bool(
            self._conn.execute(
                text(
                    "UPDATE receipts SET status = 'failed', updated_at = now() "
                    "WHERE id = :id AND status = 'processing' AND processing_attempt = :attempt"
                ),
                {"id": receipt_id, "attempt": attempt},
            ).rowcount
        )

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

    def file_paths(self) -> set[str]:
        return set(self._conn.execute(text("SELECT file_path FROM receipts WHERE file_path IS NOT NULL")).scalars())

    def category_history(self, name_keys: Sequence[str]) -> dict[str, list[int]]:
        if not name_keys:
            return {}
        rows = self._conn.execute(
            text(
                f"""
                SELECT {_NAME_KEY} AS key, ri.category_id
                FROM receipt_items ri
                JOIN receipts r ON r.id = ri.receipt_id
                WHERE r.status = 'confirmed' AND ri.category_id IS NOT NULL AND ri.normalized_name IS NOT NULL
                  AND {_NAME_KEY} = ANY(:keys)
                ORDER BY ri.id
                """
            ),
            {"keys": list(name_keys)},
        ).all()
        history: dict[str, list[int]] = {}
        for row in rows:
            history.setdefault(row.key, []).append(row.category_id)
        return history

    def known_item_names(self, limit: int, max_words: int) -> list[str]:
        # The word count is filtered here, before LIMIT, so older short names are still found when many newer names
        # are too long (third code review, issue 3), and at most `limit` names are ever loaded. Words are split on
        # runs of whitespace after trimming, as Python's str.split() does; a test checks the two agree.
        return list(
            self._conn.execute(
                text(
                    r"""
                    SELECT ri.normalized_name
                    FROM receipt_items ri
                    JOIN receipts r ON r.id = ri.receipt_id
                    WHERE r.status = 'confirmed' AND ri.normalized_name IS NOT NULL
                      AND array_length(regexp_split_to_array(btrim(ri.normalized_name), '\s+'), 1) <= :max_words
                    GROUP BY ri.normalized_name
                    ORDER BY max(ri.id) DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit, "max_words": max_words},
            ).scalars()
        )

    def _replace_lines(self, receipt_id: int, lines: Sequence[ReceiptLine]) -> None:
        self._conn.execute(text("DELETE FROM receipt_items WHERE receipt_id = :id"), {"id": receipt_id})
        if not lines:
            return
        self._conn.execute(
            text(
                """
                INSERT INTO receipt_items (receipt_id, user_id, category_id, description, normalized_name, brand,
                                           size_amount, size_unit, quantity, unit_price, line_total)
                VALUES (:receipt_id, app_user_id(), :category_id, :description, :normalized_name, :brand,
                        :size_amount, :size_unit, :quantity, :unit_price, :line_total)
                """
            ),
            [
                {
                    "receipt_id": receipt_id,
                    "category_id": line.category_id,
                    "description": line.description,
                    "normalized_name": line.normalized_name,
                    "brand": line.brand,
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
