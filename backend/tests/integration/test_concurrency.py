"""Two transactions of the same user at once (second code review, 2026-10-16, batch 3).

Each test forces the dangerous order step by step: one transaction is held open at the risky point, and the test
waits until PostgreSQL reports the other one blocked on a lock (or past the risky point) before letting the first
continue. Nothing depends on timing luck.
"""

import threading
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event, text

from app.application.budgets.dtos import SetBudgetRequest
from app.application.notifications.budget_alerts import BudgetAlerts
from app.application.receipts.dtos import ConfirmReceiptRequest, UploadReceiptRequest
from app.domain.receipts.errors import ExtractionFailed
from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt
from app.domain.receipts.receipt import ReceiptLine
from app.domain.receipts.status import ReceiptStatus
from app.domain.shared.currency import Currency
from app.infrastructure.config import Settings
from app.infrastructure.database.category_repository import SqlCategoryRepository
from app.infrastructure.database.connection import user_scoped_connection
from app.infrastructure.database.receipt_repository import SqlReceiptRepository
from app.infrastructure.database.vendor_repository import SqlVendorRepository
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeReceiptExtractor
from tests.integration.concurrency import Background, someone_waits_on_a_lock, wait_for

TODAY = date(2026, 10, 5)  # day 5: pace is low-confidence, so only the 80% and 100% alerts can fire


@pytest.fixture
def container(engine, tmp_path):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    return build_container(settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path),
                           today=lambda: TODAY)  # fmt: skip


def groceries_id(engine, user_id) -> int:
    with user_scoped_connection(engine, user_id) as conn:
        return conn.execute(text("SELECT id FROM categories WHERE name = 'Groceries' AND user_id IS NULL")).scalar_one()


def receipt(amount: str, category_id: int) -> ConfirmReceiptRequest:
    return ConfirmReceiptRequest(
        vendor_name="Spinneys", receipt_date=date(2026, 10, 3), currency="USD", total=Decimal(amount),
        primary_category_id=None, lines=[ReceiptLine("groceries", Decimal(amount), category_id=category_id)],
    )  # fmt: skip


def budget(limit: str, category_id: int) -> SetBudgetRequest:
    return SetBudgetRequest(category_id, 2026, 10, Currency.USD, Decimal(limit))


def notification_kinds(engine, user_id) -> list[str]:
    with user_scoped_connection(engine, user_id) as conn:
        return list(conn.execute(text("SELECT kind FROM notifications ORDER BY id")).scalars())

# --- Finding 7: two confirmations creating the same new vendor ---


def test_two_transactions_creating_the_same_new_vendor_both_succeed(engine, alice):
    def second_transaction():
        with user_scoped_connection(engine, alice) as conn:
            vendor_id = SqlVendorRepository(conn).find_or_create("abu ali  ")  # same vendor, other spelling
            # The transaction must still be usable afterwards, so the rest of the receipt can be saved.
            conn.execute(text("SELECT 1"))
            return vendor_id

    with user_scoped_connection(engine, alice) as conn:
        first_id = SqlVendorRepository(conn).find_or_create("Abu Ali")  # inserted, not committed yet
        # The second transaction's lookup cannot see that row, so it tries to insert too and must wait on the
        # unique index until this transaction ends.
        second = Background(second_transaction)
        wait_for(lambda: someone_waits_on_a_lock(engine) or second.done, "the second insert to block")
    second_id = second.join()

    assert second_id == first_id
    with user_scoped_connection(engine, alice) as conn:
        assert conn.execute(text("SELECT count(*) FROM vendors")).scalar_one() == 1


def test_a_vendor_created_by_another_user_is_not_reused(engine, alice, bob):
    with user_scoped_connection(engine, alice) as conn:
        alice_vendor = SqlVendorRepository(conn).find_or_create("Spinneys")
    with user_scoped_connection(engine, bob) as conn:
        bob_vendor = SqlVendorRepository(conn).find_or_create("spinneys")
        assert SqlVendorRepository(conn).find_or_create(" SPINNEYS ") == bob_vendor
    assert bob_vendor != alice_vendor


# --- Finding 8: two changes at once must not both miss a budget alert ---
# Each change on its own stays under 80% of the budget; together they pass it. Before the fix each transaction
# checked the budget without seeing the other's uncommitted receipt, both saw "under 80%", and no alert was ever
# sent. Both changes below are held after their budget check and before committing, so that is exactly the order
# the old code allowed.

def _scenarios():
    def two_new_receipts(receipts, budgets, user, cat):
        budgets.set_budget(user, budget("100", cat))
        receipts.create_manual(user, receipt("60", cat))
        return (lambda: receipts.create_manual(user, receipt("15", cat)),
                lambda: receipts.create_manual(user, receipt("15", cat)))  # fmt: skip

    def a_correction_and_a_new_receipt(receipts, budgets, user, cat):
        budgets.set_budget(user, budget("100", cat))
        receipts.create_manual(user, receipt("60", cat))
        small = receipts.create_manual(user, receipt("1", cat)).receipt.id
        return (lambda: receipts.confirm(user, small, receipt("16", cat)),  # 1 -> 16
                lambda: receipts.create_manual(user, receipt("15", cat)))  # fmt: skip

    def a_lower_budget_and_a_new_receipt(receipts, budgets, user, cat):
        budgets.set_budget(user, budget("200", cat))
        receipts.create_manual(user, receipt("70", cat))
        return (lambda: budgets.set_budget(user, budget("100", cat)),  # 70 of 100 alone
                lambda: receipts.create_manual(user, receipt("15", cat)))  # 85 of 200 alone  # fmt: skip

    return [two_new_receipts, a_correction_and_a_new_receipt, a_lower_budget_and_a_new_receipt]


@pytest.mark.parametrize("scenario", _scenarios(), ids=lambda s: s.__name__)
def test_concurrent_changes_do_not_miss_a_budget_alert(container, engine, alice, monkeypatch, scenario):
    first_change, second_change = scenario(container.receipts, container.budgets, alice, groceries_id(engine, alice))
    assert notification_kinds(engine, alice) == []  # nothing so far

    real_check = BudgetAlerts.check
    a_checked, b_checked = threading.Event(), threading.Event()

    def check_then_hold(self, work):
        real_check(self, work)
        if threading.current_thread().name == "A":  # hold A open until B has checked too, or is made to wait
            a_checked.set()
            wait_for(lambda: b_checked.is_set() or someone_waits_on_a_lock(engine), "B to check or to wait for A")
        elif threading.current_thread().name == "B":
            b_checked.set()

    monkeypatch.setattr(BudgetAlerts, "check", check_then_hold)
    first = Background(first_change, name="A")
    wait_for(a_checked.is_set, "A to check the budget")
    second = Background(second_change, name="B")
    first.join()
    second.join()

    assert notification_kinds(engine, alice) == ["budget_near"]  # sent once, by whichever change came second


# --- Finding 9: a receipt is read as one version, never header from one and lines from another ---
# The writer commits a correction (total 100 -> 200, lines changed to match) or deletes the receipt right after
# the reader's statement that reads receipt headers. A reader that fetched the lines in a second statement then
# combined the old header with the new lines (a made-up -100 "tax and discounts"), or with no lines at all.

@pytest.fixture
def receipt_of_100(container, engine, alice):
    cat = groceries_id(engine, alice)
    two_lines = ConfirmReceiptRequest(
        vendor_name="Spinneys", receipt_date=date(2026, 10, 3), currency="USD", total=Decimal("100"),
        primary_category_id=None,
        lines=[ReceiptLine("milk", Decimal("60"), category_id=cat), ReceiptLine("bread", Decimal("40"))],
    )  # fmt: skip
    return container.receipts.create_manual(alice, two_lines).receipt.id


def correct_to_200(container, alice, receipt_id):
    request = ConfirmReceiptRequest(
        vendor_name="Spinneys", receipt_date=date(2026, 10, 3), currency="USD", total=Decimal("200"),
        primary_category_id=None, lines=[ReceiptLine("cheese", Decimal("200"))],
    )  # fmt: skip
    container.receipts.confirm(alice, receipt_id, request)


def read_with_a_change_after_the_header(engine, alice, read, change):
    """Run `read` on a fresh connection; the first time it reads receipt headers, `change` commits."""
    done = []

    def after_execute(conn, cursor, statement, parameters, context, executemany):
        if not done and "FROM receipts r" in statement:
            done.append(True)
            change()

    with user_scoped_connection(engine, alice) as conn:
        event.listen(conn, "after_cursor_execute", after_execute)
        result = read(SqlReceiptRepository(conn))
    assert done, "the change never ran"
    return result


@pytest.mark.parametrize("change", ["correct", "delete"])
@pytest.mark.parametrize("read", ["get", "list_confirmed_between"])
def test_a_reader_sees_one_whole_version_of_a_receipt(container, engine, alice, receipt_of_100, read, change):
    def make_change():
        if change == "correct":
            correct_to_200(container, alice, receipt_of_100)
        else:
            container.receipts.delete(alice, receipt_of_100)

    def do_read(repo):
        if read == "get":
            return repo.get(receipt_of_100)
        (only,) = repo.list_confirmed_between(date(2026, 10, 1), date(2026, 11, 1))
        return only

    seen = read_with_a_change_after_the_header(engine, alice, do_read, make_change)

    old = (Decimal("100"), [("milk", Decimal("60")), ("bread", Decimal("40"))])
    new = (Decimal("200"), [("cheese", Decimal("200"))])
    assert (seen.total, [(line.description, line.line_total) for line in seen.lines]) in (old, new)


def test_spending_never_invents_an_adjustment_from_two_versions(container, engine, alice, receipt_of_100):
    def read(repo):
        receipts = repo.list_confirmed_between(date(2026, 10, 1), date(2026, 11, 1))
        return sum(r.total for r in receipts) - sum(r.lines_total for r in receipts)  # "tax, discounts & rounding"

    adjustment = read_with_a_change_after_the_header(engine, alice, read, lambda: correct_to_200(container, alice,
                                                                                                    receipt_of_100))
    assert adjustment == 0  # both versions add up exactly


# --- Finding 10: only one worker owns a receipt's reading, and a stale or orphaned result is discarded ---

DRAFT = ExtractedReceipt(
    vendor_name="Spinneys", receipt_date=date(2026, 10, 3), currency="USD", total=Decimal("2.50"),
    lines=(ExtractedLine(description="LABAN", line_total=Decimal("2.50")),),
)  # fmt: skip
EMPTY_DRAFT = ExtractedReceipt(vendor_name="Spinneys", total=Decimal("2.50"), lines=())


class ScriptedExtractor:
    """A vision model whose answer (or failure) is decided by the test, which can also act while it 'reads'."""

    def __init__(self, result=DRAFT, while_reading=None) -> None:
        self.result = result
        self.while_reading = while_reading or (lambda: None)
        self.calls = 0

    def extract(self, content, content_type, category_names):
        self.calls += 1
        self.while_reading()
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def uploaded_receipt(container, user_id) -> int:
    return container.receipts.upload(user_id, UploadReceiptRequest(b"receipt-image", "image/jpeg")).receipt.id


def receipt_row(engine, user_id, receipt_id):
    with user_scoped_connection(engine, user_id) as conn:
        return conn.execute(
            text("SELECT status, total, (SELECT count(*) FROM receipt_items WHERE receipt_id = r.id) AS lines "
                 "FROM receipts r WHERE id = :id"), {"id": receipt_id},
        ).one_or_none()  # fmt: skip


@pytest.fixture
def scripted(container):
    extractor = ScriptedExtractor()
    container.receipts._extractor = extractor  # the same service, with a model the test controls
    return extractor


def test_two_simultaneous_process_calls_read_the_receipt_once(container, engine, alice, scripted, monkeypatch):
    receipt_id = uploaded_receipt(container, alice)
    real_list_all = SqlCategoryRepository.list_all
    a_claimed, b_finished = threading.Event(), threading.Event()

    def list_all_then_hold(self):  # runs inside the claiming transaction, after the claim
        if threading.current_thread().name == "A":
            a_claimed.set()
            wait_for(lambda: someone_waits_on_a_lock(engine) or b_finished.is_set(), "B to try to claim too")
        return real_list_all(self)

    def second_call():
        try:
            container.receipts.process(alice, receipt_id)
        finally:
            b_finished.set()

    monkeypatch.setattr(SqlCategoryRepository, "list_all", list_all_then_hold)
    first = Background(lambda: container.receipts.process(alice, receipt_id), name="A")
    wait_for(a_claimed.is_set, "A to claim the receipt")
    second = Background(second_call, name="B")
    first.join()
    second.join()

    assert scripted.calls == 1  # the model was asked once
    assert receipt_row(engine, alice, receipt_id).status == "needs_review"
    assert notification_kinds(engine, alice) == ["receipt_ready"]


@pytest.mark.parametrize("result", [DRAFT, EMPTY_DRAFT, ExtractionFailed("unreadable")], ids=["lines", "no lines",
                                                                                             "failure"])
def test_a_receipt_deleted_while_being_read_stays_deleted_and_gets_no_notification(
    container, engine, alice, scripted, result
):
    receipt_id = uploaded_receipt(container, alice)
    scripted.result = result
    scripted.while_reading = lambda: container.receipts.delete(alice, receipt_id)

    container.receipts.process(alice, receipt_id)

    assert receipt_row(engine, alice, receipt_id) is None
    assert notification_kinds(engine, alice) == []  # no "ready" or "failed" for a receipt that no longer exists


def finish_elsewhere_and_confirm(container, engine, alice, receipt_id):
    """While the model is still reading, the receipt is finished another way: here a recovery step gives up on it
    (failed) and the user types it in and confirms it."""
    with user_scoped_connection(engine, alice) as conn:
        conn.execute(text("UPDATE receipts SET status = 'failed' WHERE id = :id"), {"id": receipt_id})
    container.receipts.confirm(alice, receipt_id, receipt("9.99", groceries_id(engine, alice)))


@pytest.mark.parametrize("result", [DRAFT, EMPTY_DRAFT, ExtractionFailed("unreadable")], ids=["late success",
                                                                                             "late empty success",
                                                                                             "late failure"])
def test_a_late_result_never_overwrites_a_receipt_the_user_already_confirmed(
    container, engine, alice, scripted, result
):
    receipt_id = uploaded_receipt(container, alice)
    scripted.result = result
    scripted.while_reading = lambda: finish_elsewhere_and_confirm(container, engine, alice, receipt_id)

    container.receipts.process(alice, receipt_id)

    row = receipt_row(engine, alice, receipt_id)
    assert (row.status, row.total, row.lines) == ("confirmed", Decimal("9.99"), 1)  # the user's values
    assert notification_kinds(engine, alice) == []


def test_normal_reading_and_the_manual_fallback_still_work(container, engine, alice, scripted):
    ok = uploaded_receipt(container, alice)
    container.receipts.process(alice, ok)
    assert receipt_row(engine, alice, ok).status == "needs_review"

    scripted.result = ExtractionFailed("unreadable")
    container.receipts.upload(alice, UploadReceiptRequest(b"other-image", "image/jpeg"))
    bad = max(r.id for r in container.receipts.list_all(alice))
    container.receipts.process(alice, bad)
    assert receipt_row(engine, alice, bad).status == "failed"
    container.receipts.confirm(alice, bad, receipt("3", groceries_id(engine, alice)))  # typed in by hand
    assert receipt_row(engine, alice, bad).status == "confirmed"
    assert notification_kinds(engine, alice) == ["receipt_ready", "receipt_failed"]


def test_only_the_current_attempt_may_finish_a_receipt(container, engine, alice):
    # No recovery job exists yet; this stands in for one that claims a receipt stuck in `processing` again.
    # The old worker must then lose: neither its draft nor its failure may be saved.
    receipt_id = uploaded_receipt(container, alice)
    with user_scoped_connection(engine, alice) as conn:
        old = SqlReceiptRepository(conn).claim_for_processing(receipt_id, [ReceiptStatus.UPLOADED])
        assert SqlReceiptRepository(conn).claim_for_processing(receipt_id, [ReceiptStatus.UPLOADED]) is None
        conn.execute(text("UPDATE receipts SET processing_attempt = processing_attempt + 1 WHERE id = :id"),
                     {"id": receipt_id})  # fmt: skip
    newer_attempt = old.attempt + 1

    with user_scoped_connection(engine, alice) as conn:
        repo = SqlReceiptRepository(conn)
        assert repo.save_extraction(receipt_id, old.attempt, DRAFT, None, []) is False
        assert repo.fail_processing(receipt_id, old.attempt) is False
        assert repo.get(receipt_id).status.value == "processing"  # untouched by the old worker
        assert repo.save_extraction(receipt_id, newer_attempt, DRAFT, None, []) is True
        assert repo.get(receipt_id).status.value == "needs_review"
