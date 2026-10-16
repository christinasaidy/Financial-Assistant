"""Second code review (2026-10-16), checked through the real API and database."""

import os
import time
import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt
from app.infrastructure.config import Settings
from app.infrastructure.extraction.parsing import parse_extraction
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeReceiptExtractor

SPINNEYS = ExtractedReceipt(
    vendor_name="Spinneys",
    receipt_date=date(2026, 10, 15),
    currency="USD",
    total=Decimal("9.37"),
    lines=(ExtractedLine(description="MILK", line_total=Decimal("9.37")),),
)


class RawAnswerExtractor:
    """Feeds a raw model answer through the real schema check, as the Gemini adapter does."""

    def __init__(self, answer: dict) -> None:
        self.answer = answer
        self.calls = 0

    def extract(self, content, content_type, category_names) -> ExtractedReceipt:
        self.calls += 1
        return parse_extraction(self.answer)


@pytest.fixture
def make_client(engine, tmp_path):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")

    def _make(extractor=None) -> TestClient:
        container = build_container(
            settings, extractor=extractor or FakeReceiptExtractor(SPINNEYS), storage=LocalFileStorage(tmp_path)
        )
        return TestClient(create_app(container))

    return _make


@pytest.fixture
def client(make_client):
    return make_client()


@pytest.fixture
def alice(client, engine):
    email = f"{uuid.uuid4()}@test.local"
    body = {"email": email, "password": "correct-horse"}
    assert client.post("/auth/register", json=body).status_code == 201
    yield {"Authorization": "Bearer " + client.post("/auth/login", json=body).json()["access_token"]}
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


def manual(client, headers, **overrides):
    body = {"receipt_date": "2026-10-15", "currency": "USD", "total": "1", **overrides}
    return client.post("/receipts/manual", json=body, headers=headers)


# --- Finding 2: text PostgreSQL cannot store gets a clear 422, never a database error ---

NUL_FIELDS = [
    {"lines": [{"description": "milk\u0000", "line_total": "1"}]},  # the review's example
    {"lines": [{"description": "milk", "normalized_name": "mi\u0000lk", "line_total": "1"}]},
    {"vendor_name": "Spin\u0000neys"},
]


@pytest.mark.parametrize("overrides", NUL_FIELDS)
def test_manual_entry_with_a_nul_character_is_refused_and_nothing_is_saved(client, alice, overrides):
    response = manual(client, alice, **overrides)
    assert response.status_code == 422, response.text
    assert "character" in response.json()["detail"]
    assert client.get("/receipts", headers=alice).json() == []


@pytest.mark.parametrize("overrides", NUL_FIELDS)
def test_a_correction_with_a_nul_character_leaves_the_receipt_as_it_was(client, alice, overrides):
    lines = [{"description": "laban", "normalized_name": "laban", "line_total": "1"}]
    before = manual(client, alice, vendor_name="Spinneys", lines=lines, lbp_per_usd="90000").json()

    body = {"receipt_date": "2026-10-16", "currency": "LBP", "total": "1", "vendor_name": "Carrefour", **overrides}
    response = client.post(f"/receipts/{before['id']}/confirm", json=body, headers=alice)

    assert response.status_code == 422, response.text
    after = client.get(f"/receipts/{before['id']}", headers=alice).json()
    assert after == before  # date, currency, vendor, lines and the saved rate all unchanged
    assert after["lbp_per_usd"] == "90000.000000"


def test_arabic_french_and_english_text_is_kept_exactly(client, alice):
    lines = [
        {"description": "لبن عيران ١ لتر", "normalized_name": "laban", "line_total": "1"},
        {"description": "Pâté de campagne – 200 g", "normalized_name": "pâté", "line_total": "0"},
        {"description": "TOMATO\tPASTE  x2", "line_total": "0"},  # ordinary inner whitespace is not touched
    ]
    response = manual(client, alice, vendor_name="Le Charcutier Aoun", lines=lines)
    assert response.status_code == 201, response.text
    receipt = response.json()
    assert receipt["vendor_name"] == "Le Charcutier Aoun"
    assert [line["description"] for line in receipt["lines"]] == [line["description"] for line in lines]
    assert [line["normalized_name"] for line in receipt["lines"]] == ["laban", "pâté", None]


@pytest.mark.parametrize(
    "answer",
    [
        {"vendor_name": "Spin\u0000neys", "lines": []},
        {"lines": [{"description": "MILK\u0000", "line_total": "1"}]},
        {"lines": [{"description": "MILK", "normalized_name": "mi\u0000lk", "line_total": "1"}]},
        {"lines": [{"description": "MILK", "line_total": "1", "category": "Groceries\u0000"}]},
    ],
)
def test_a_model_answer_with_a_nul_character_is_retried_then_fails_for_manual_entry(make_client, alice, answer):
    extractor = RawAnswerExtractor(answer)
    client = make_client(extractor)
    receipt_id = client.post("/receipts", files={"file": ("r", b"img", "image/png")}, headers=alice).json()["id"]

    assert client.get(f"/receipts/{receipt_id}", headers=alice).json()["status"] == "failed"
    assert extractor.calls == 2  # one retry, as for any unusable answer
    kinds = [n["kind"] for n in client.get("/notifications", headers=alice).json()["items"]]
    assert kinds == ["receipt_failed"]
    # ...and the user can still type it in.
    body = {"receipt_date": "2026-10-15", "currency": "USD", "total": "1"}
    assert client.post(f"/receipts/{receipt_id}/confirm", json=body, headers=alice).status_code == 200


# --- Finding 11: file failures never lose a committed receipt's image, and never become a user-facing error ---


def stored_files(tmp_path) -> list:
    return [p for p in tmp_path.rglob("*") if p.is_file()]


def upload(client, headers):
    return client.post("/receipts", files={"file": ("r", b"img", "image/png")}, headers=headers)


def test_a_file_that_cannot_be_removed_after_deleting_the_receipt_is_logged_not_an_error(
    client, alice, tmp_path, monkeypatch, caplog
):
    receipt_id = upload(client, alice).json()["id"]

    def locked(self, path):
        raise PermissionError("file is open in another program")

    monkeypatch.setattr(LocalFileStorage, "delete", locked)
    assert client.delete(f"/receipts/{receipt_id}", headers=alice).status_code == 204  # the receipt is gone
    assert client.get(f"/receipts/{receipt_id}", headers=alice).status_code == 404
    assert len(stored_files(tmp_path)) == 1  # left for the orphan clean-up, not lost silently
    assert "Could not remove" in caplog.text


def test_when_saving_the_receipt_fails_its_file_is_removed_and_the_real_error_is_kept(
    client, alice, tmp_path, monkeypatch
):
    from app.infrastructure.database.receipt_repository import SqlReceiptRepository

    def database_down(self, *args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(SqlReceiptRepository, "create", database_down)
    with pytest.raises(RuntimeError, match="database went away"):
        upload(client, alice)
    assert stored_files(tmp_path) == []  # nothing was committed, so removing the file was safe

    def locked(self, path):
        raise PermissionError("file is open in another program")

    monkeypatch.setattr(LocalFileStorage, "delete", locked)
    with pytest.raises(RuntimeError, match="database went away"):  # not hidden by the clean-up failing too
        upload(client, alice)


def test_an_error_reported_after_the_commit_never_deletes_the_saved_receipts_file(
    client, alice, tmp_path, monkeypatch
):
    # A connection lost while committing: the receipt may well be saved. Its file must stay; if the receipt was
    # in fact not saved, the file is an orphan the clean-up can find later.
    import app.infrastructure.database.unit_of_work as unit_of_work

    real = unit_of_work.user_scoped_connection

    @contextmanager
    def commit_then_report_failure(engine, user_id):
        with real(engine, user_id) as conn:
            yield conn
        raise ConnectionError("server closed the connection during COMMIT")

    monkeypatch.setattr(unit_of_work, "user_scoped_connection", commit_then_report_failure)
    with pytest.raises(ConnectionError):
        upload(client, alice)
    monkeypatch.undo()

    (receipt,) = client.get("/receipts", headers=alice).json()  # it was committed
    assert receipt["has_file"] is True
    assert len(stored_files(tmp_path)) == 1  # and its image is still there


# --- Finding 11: the orphan clean-up finds exactly the files no receipt points at, and nothing else ---


def make_old(path, days=2):
    when = time.time() - days * 24 * 3600
    os.utime(path, (when, when))


def test_the_orphan_clean_up_removes_only_unreferenced_old_files_of_the_app(engine, tmp_path, alice, monkeypatch):
    import app.infrastructure.database.unit_of_work as unit_of_work
    from app.clean_files import main as clean_files

    storage = LocalFileStorage(tmp_path)
    container = build_container(Settings(), extractor=FakeReceiptExtractor(SPINNEYS), storage=storage)
    client = TestClient(create_app(container))

    def upload_bytes(content, headers=alice):
        return client.post("/receipts", files={"file": ("r", content, "image/png")}, headers=headers)

    def files_of(user_id):
        return {file.path for file in storage.list_files(user_id)}

    # 1. A normal, committed receipt: its file must survive.
    kept_id = upload_bytes(b"kept").json()["id"]
    (alice_id,) = storage.user_ids()
    kept_file = files_of(alice_id).pop()

    # 2. A receipt deleted while its file could not be removed.
    gone_id = upload_bytes(b"gone").json()["id"]
    gone_file = (files_of(alice_id) - {kept_file}).pop()
    with monkeypatch.context() as patch:
        patch.setattr(LocalFileStorage, "delete", lambda self, path: (_ for _ in ()).throw(PermissionError("locked")))
        assert client.delete(f"/receipts/{gone_id}", headers=alice).status_code == 204

    # 3. An upload whose commit failed (rolled back): the file was kept because the outcome looked uncertain.
    real = unit_of_work.user_scoped_connection

    @contextmanager
    def commit_fails(engine, user_id):
        with real(engine, user_id) as conn:
            yield conn
            raise ConnectionError("lost before COMMIT")  # inside: the transaction rolls back

    with monkeypatch.context() as patch:
        patch.setattr(unit_of_work, "user_scoped_connection", commit_fails)
        with pytest.raises(ConnectionError):
            upload_bytes(b"never saved")
    unsaved_file = (files_of(alice_id) - {kept_file, gone_file}).pop()

    # 4. A half-written file, 5. a recent orphan, 6. things that are not the app's files.
    folder = tmp_path / str(alice_id)
    partial = folder / (".partial-" + "a" * 32 + ".jpg")
    partial.write_bytes(b"half")
    recent = folder / ("b" * 32 + ".jpg")
    recent.write_bytes(b"just uploaded, receipt not committed yet")
    strangers = [folder / "notes.txt", tmp_path / "backups" / ("c" * 32 + ".jpg")]
    strangers[1].parent.mkdir()
    for stranger in strangers:
        stranger.write_bytes(b"not ours")

    # 7. Another user's committed receipt, checked as that user.
    bob = {"email": f"{uuid.uuid4()}@test.local", "password": "correct-horse"}
    assert client.post("/auth/register", json=bob).status_code == 201
    bob_headers = {"Authorization": "Bearer " + client.post("/auth/login", json=bob).json()["access_token"]}
    try:
        upload_bytes(b"bob's", bob_headers)
        for file in [p for p in tmp_path.rglob("*") if p.is_file() and p != recent]:
            make_old(file)

        expected = {gone_file, unsaved_file, f"{alice_id}/{partial.name}"}
        assert {path for paths in container.receipts.find_orphaned_files().values() for path in paths} == expected

        assert clean_files([], container) == 0  # a dry run removes nothing
        assert sorted(container.receipts.find_orphaned_files()[alice_id]) == sorted(expected)
        assert clean_files(["--delete"], container) == 0
        assert container.receipts.find_orphaned_files() == {}

        assert files_of(alice_id) == {kept_file, f"{alice_id}/{recent.name}"}  # only the orphans went
        assert storage.read(kept_file) == b"kept"
        assert client.get(f"/receipts/{kept_id}", headers=alice).status_code == 200
        assert all(stranger.exists() for stranger in strangers)
        assert len(storage.list_files(storage.user_ids()[-1])) == 1  # bob's file untouched
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": bob["email"]})
