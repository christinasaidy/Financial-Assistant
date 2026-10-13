from enum import StrEnum

from app.domain.receipts.errors import InvalidStateTransition


class ReceiptStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    FAILED = "failed"


# uploaded -> processing -> needs_review -> confirmed, or processing -> failed.
# A failed receipt can still be filled in by hand, which moves it to needs_review.
_ALLOWED: dict[ReceiptStatus, frozenset[ReceiptStatus]] = {
    ReceiptStatus.UPLOADED: frozenset({ReceiptStatus.PROCESSING}),
    ReceiptStatus.PROCESSING: frozenset({ReceiptStatus.NEEDS_REVIEW, ReceiptStatus.FAILED}),
    ReceiptStatus.NEEDS_REVIEW: frozenset({ReceiptStatus.CONFIRMED}),
    ReceiptStatus.CONFIRMED: frozenset(),
    ReceiptStatus.FAILED: frozenset({ReceiptStatus.NEEDS_REVIEW}),
}


def can_transition(current: ReceiptStatus, target: ReceiptStatus) -> bool:
    return target in _ALLOWED[current]


def transition(current: ReceiptStatus, target: ReceiptStatus) -> ReceiptStatus:
    """Return `target` if the move is allowed, otherwise raise InvalidStateTransition."""
    if not can_transition(current, target):
        raise InvalidStateTransition(current, target)
    return target
