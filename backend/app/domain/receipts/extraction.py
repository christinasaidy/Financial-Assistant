"""What the vision model returns for a receipt, and how it becomes draft lines for review."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from app.domain.receipts.categorization import suggest_category
from app.domain.receipts.normalization import normalize_product_name, normalize_size
from app.domain.receipts.receipt import ReceiptLine
from app.domain.shared.decimals import MONEY_PLACES, QUANTITY_PLACES, rounded


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


def rounded_for_storage(extracted: ExtractedReceipt) -> ExtractedReceipt:
    """Round what the model read to the precision the database stores (money 2 places, quantities 3).
    Unlike typed input, this is rounded rather than refused, because the user reviews it next.

    Sizes are left in the model's unit here: the stored precision is in base units, so `to_draft_lines`
    rounds them after converting (0.3333 L is 333.300 ml, not 0.333 L = 333.000 ml)."""
    return replace(
        extracted,
        total=rounded(extracted.total, MONEY_PLACES) if extracted.total is not None else None,
        lines=tuple(
            replace(
                line,
                line_total=rounded(line.line_total, MONEY_PLACES),
                quantity=rounded(line.quantity, QUANTITY_PLACES),
                unit_price=rounded(line.unit_price, MONEY_PLACES) if line.unit_price is not None else None,
            )
            for line in extracted.lines
        ),
    )


def _stored_size(amount: Decimal | None, unit: str | None) -> tuple[Decimal | None, str | None]:
    """The model's size in a base unit, rounded to the stored 3 places. A size too small to store even in
    base units (0.0004 ml) is dropped like any other unusable size: sizes are optional, the line is kept."""
    base_amount, base_unit = normalize_size(amount, unit)
    if base_amount is None:
        return None, None
    stored = rounded(base_amount, QUANTITY_PLACES)
    return (stored, base_unit) if stored > 0 else (None, None)


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
        size_amount, size_unit = _stored_size(line.size_amount, line.size_unit)
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
