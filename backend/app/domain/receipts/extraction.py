"""What the vision model returns for a receipt, and how it becomes draft lines for review."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.receipts.categorization import suggest_category
from app.domain.receipts.normalization import normalize_product_name, normalize_size
from app.domain.receipts.receipt import ReceiptLine


@dataclass(frozen=True)
class ExtractedLine:
    description: str
    line_total: Decimal
    quantity: Decimal = Decimal(1)
    unit_price: Decimal | None = None
    normalized_name: str | None = None
    size_amount: Decimal | None = None
    size_unit: str | None = None
    category: str | None = None  # a category name suggested by the model


@dataclass(frozen=True)
class ExtractedReceipt:
    vendor_name: str | None = None
    receipt_date: date | None = None
    currency: str | None = None
    total: Decimal | None = None
    lines: tuple[ExtractedLine, ...] = ()


def to_draft_lines(
    extracted: ExtractedReceipt,
    category_history: Mapping[str, Sequence[int]],
    category_ids_by_name: Mapping[str, int],
) -> tuple[ReceiptLine, ...]:
    """Normalise extracted lines and choose each one's suggested category.

    Category memory comes first: the category the user most often confirmed for the same
    normalized name. Only when there is no history does the model's own suggestion apply.
    """
    lines = []
    for line in extracted.lines:
        name = normalize_product_name(line.normalized_name)
        size_amount, size_unit = normalize_size(line.size_amount, line.size_unit)
        category_id = suggest_category(category_history.get(name, ())) if name else None
        if category_id is None and line.category:
            category_id = category_ids_by_name.get(line.category.strip().lower())
        lines.append(
            ReceiptLine(
                description=line.description.strip(),
                line_total=line.line_total,
                quantity=line.quantity,
                unit_price=line.unit_price,
                normalized_name=name,
                size_amount=size_amount,
                size_unit=size_unit,
                category_id=category_id,
            )
        )
    return tuple(lines)
