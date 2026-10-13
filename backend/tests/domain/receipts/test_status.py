import pytest

from app.domain.receipts.errors import InvalidStateTransition
from app.domain.receipts.status import ReceiptStatus, can_transition, transition


def test_happy_path_to_confirmed():
    status = ReceiptStatus.UPLOADED
    for target in (ReceiptStatus.PROCESSING, ReceiptStatus.NEEDS_REVIEW, ReceiptStatus.CONFIRMED):
        status = transition(status, target)
    assert status is ReceiptStatus.CONFIRMED


def test_processing_can_fail():
    assert transition(ReceiptStatus.PROCESSING, ReceiptStatus.FAILED) is ReceiptStatus.FAILED


def test_failed_receipt_can_be_filled_in_by_hand():
    status = transition(ReceiptStatus.FAILED, ReceiptStatus.NEEDS_REVIEW)
    assert transition(status, ReceiptStatus.CONFIRMED) is ReceiptStatus.CONFIRMED


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ReceiptStatus.UPLOADED, ReceiptStatus.CONFIRMED),
        (ReceiptStatus.UPLOADED, ReceiptStatus.NEEDS_REVIEW),
        (ReceiptStatus.NEEDS_REVIEW, ReceiptStatus.PROCESSING),
        (ReceiptStatus.CONFIRMED, ReceiptStatus.NEEDS_REVIEW),
        (ReceiptStatus.FAILED, ReceiptStatus.PROCESSING),
        (ReceiptStatus.FAILED, ReceiptStatus.CONFIRMED),
    ],
)
def test_disallowed_transitions_raise(current, target):
    assert not can_transition(current, target)
    with pytest.raises(InvalidStateTransition):
        transition(current, target)
