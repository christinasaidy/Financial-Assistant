"""The receipt flow through the real API and database, with a fake vision model and a temp folder."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.application.receipts.dtos import UploadReceiptRequest
from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import user_scoped_connection
from app.infrastructure.database.receipt_repository import SqlReceiptRepository
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeReceiptExtractor

# Lines add up to 6.00 but the total says 6.60, as on a real receipt with tax.
SAMPLE = ExtractedReceipt(
    vendor_name="Spinneys",
    receipt_date=date(2026, 10, 1),
    currency="USD",
    total=Decimal("6.60"),
    lines=(
        ExtractedLine(
            description="LABAN AYRAN 1L",
            line_total=Decimal("2.50"),
            normalized_name="Laban",
            size_amount=Decimal(1),
            size_unit="l",
            category="Groceries",
        ),
        ExtractedLine(description="KHOBZ", line_total=Decimal("3.50"), normalized_name="bread"),
    ),
)


@pytest.fixture
def extractor():
    return FakeReceiptExtractor(SAMPLE)


@pytest.fixture
def container(engine, extractor, tmp_path):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    return build_container(settings, extractor=extractor, storage=LocalFileStorage(tmp_path))


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


@pytest.fixture
def sign_in(client, engine):
    """Register and log in a fresh user. Returns (auth headers, user id). Users are deleted afterwards."""
    emails: list[str] = []

    def _sign_in() -> tuple[dict[str, str], int]:
        email = f"{uuid.uuid4()}@test.local"
        emails.append(email)
        body = {"email": email, "password": "correct-horse"}
        assert client.post("/auth/register", json=body).status_code == 201
        result = client.post("/auth/login", json=body).json()
        return {"Authorization": f"Bearer {result['access_token']}"}, result["user"]["id"]

    yield _sign_in

    with engine.begin() as conn:
        for email in emails:
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


@pytest.fixture
def alice(sign_in):
    return sign_in()[0]


def upload(client, headers, content=b"receipt-image", content_type="image/jpeg"):
    return client.post("/receipts", files={"file": ("receipt", content, content_type)}, headers=headers)


def category_id(client, headers, name):
    return next(c["id"] for c in client.get("/categories", headers=headers).json() if c["name"] == name)


def confirm_body(**overrides):
    body = {
        "vendor_name": "Spinneys",
        "receipt_date": "2026-10-01",
        "currency": "USD",
        "total": "6.60",
        "lines": [{"description": "LABAN AYRAN 1L", "normalized_name": "laban", "line_total": "2.50"}],
    }
    return {**body, **overrides}


def test_upload_is_read_in_the_background_and_becomes_a_draft(client, alice, extractor):
    response = upload(client, alice)
    assert response.status_code == 202
    assert response.json()["status"] == "uploaded"
    assert response.json()["has_file"] is True

    receipt = client.get(f"/receipts/{response.json()['id']}", headers=alice).json()
    assert receipt["status"] == "needs_review"
    assert receipt["vendor_name"] == "Spinneys"
    assert (receipt["receipt_date"], receipt["currency"], receipt["total"]) == ("2026-10-01", "USD", "6.60")
    assert receipt["lines_total"] == "6.00"
    assert receipt["flags"] == ["total_mismatch"]

    laban, bread = receipt["lines"]
    assert laban["description"] == "LABAN AYRAN 1L"
    assert laban["normalized_name"] == "laban"
    assert (Decimal(laban["size_amount"]), laban["size_unit"]) == (Decimal(1000), "ml")
    assert laban["category_id"] == category_id(client, alice, "Groceries")  # the model's suggestion
    assert bread["category_id"] is None

    assert "Groceries" in extractor.category_names  # the model was told which categories exist
    assert extractor.calls == 1


def test_same_file_twice_is_a_duplicate_for_that_user_only(client, alice, sign_in):
    first = upload(client, alice).json()["id"]
    again = upload(client, alice)
    assert again.status_code == 409
    assert again.json()["receipt_id"] == first

    bob, _ = sign_in()
    assert upload(client, bob).status_code == 202


def test_bad_uploads_are_refused(client, alice):
    assert upload(client, alice, content_type="text/plain").status_code == 415
    assert upload(client, alice, content=b"").status_code == 422
    assert upload(client, alice, content=b"x" * (10 * 1024 * 1024 + 1)).status_code == 413
    assert client.get("/receipts", headers=alice).json() == []


def test_confirm_saves_the_reviewed_values(client, alice):
    receipt_id = upload(client, alice).json()["id"]
    dining = category_id(client, alice, "Dining")
    body = confirm_body(
        vendor_name="  Spinneys Dbayeh ",
        total="2.50",
        primary_category_id=dining,
        lines=[
            {
                "description": " LABAN AYRAN 1L ",
                "normalized_name": " Laban ",
                "line_total": "2.50",
                "quantity": "1",
                "size_amount": "1000",
                "size_unit": "ml",
                "category_id": dining,
            }
        ],
    )
    response = client.post(f"/receipts/{receipt_id}/confirm", json=body, headers=alice)
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["status"] == "confirmed"
    assert receipt["vendor_name"] == "Spinneys Dbayeh"
    assert receipt["flags"] == []
    assert len(receipt["lines"]) == 1  # the draft lines were replaced, not added to
    assert receipt["lines"][0]["description"] == "LABAN AYRAN 1L"
    assert receipt["lines"][0]["normalized_name"] == "laban"

    listed = client.get("/receipts", headers=alice).json()
    assert [(r["id"], r["status"]) for r in listed] == [(receipt_id, "confirmed")]


def test_a_confirmed_receipt_can_be_corrected(client, alice):
    receipt_id = upload(client, alice).json()["id"]
    client.post(f"/receipts/{receipt_id}/confirm", json=confirm_body(), headers=alice)
    corrected = client.post(f"/receipts/{receipt_id}/confirm", json=confirm_body(total="7.00", lines=[]), headers=alice)
    assert corrected.status_code == 200
    assert (corrected.json()["status"], corrected.json()["total"], corrected.json()["lines"]) == ("confirmed", "7.00", [])


def test_category_memory_suggests_what_the_user_confirmed_before(client, alice):
    dining = category_id(client, alice, "Dining")
    first = upload(client, alice, content=b"first").json()["id"]
    body = confirm_body(lines=[{"description": "LABAN", "normalized_name": "laban", "line_total": "2.50", "category_id": dining}])
    assert client.post(f"/receipts/{first}/confirm", json=body, headers=alice).status_code == 200

    second = upload(client, alice, content=b"second").json()["id"]
    laban = client.get(f"/receipts/{second}", headers=alice).json()["lines"][0]
    assert laban["category_id"] == dining  # the model said Groceries, the user's own history wins


def test_unconfirmed_drafts_do_not_feed_category_memory(client, alice):
    upload(client, alice, content=b"first")  # stays a draft with the model's Groceries suggestion
    second = upload(client, alice, content=b"second").json()["id"]
    laban = client.get(f"/receipts/{second}", headers=alice).json()["lines"][0]
    assert laban["category_id"] == category_id(client, alice, "Groceries")


def test_failed_extraction_is_retried_once_then_entered_by_hand(client, alice, extractor):
    extractor.result = None
    receipt_id = upload(client, alice).json()["id"]
    assert extractor.calls == 2
    assert client.get(f"/receipts/{receipt_id}", headers=alice).json()["status"] == "failed"

    response = client.post(f"/receipts/{receipt_id}/confirm", json=confirm_body(), headers=alice)
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_manual_entry_creates_a_confirmed_receipt_without_a_file(client, alice):
    response = client.post("/receipts/manual", json=confirm_body(currency="LBP", total="450000", lines=[]), headers=alice)
    assert response.status_code == 201
    receipt = response.json()
    assert (receipt["status"], receipt["has_file"], receipt["currency"], receipt["total"]) == (
        "confirmed",
        False,
        "LBP",
        "450000.00",
    )


def test_invalid_values_are_rejected_and_nothing_is_saved(client, alice):
    receipt_id = upload(client, alice).json()["id"]
    for bad in (
        confirm_body(currency="EUR"),
        confirm_body(total="-1"),
        confirm_body(primary_category_id=999_999_999),
        confirm_body(lines=[{"description": "x", "line_total": "1", "quantity": "0"}]),
        confirm_body(lines=[{"description": "x", "line_total": "1", "size_amount": "250"}]),
    ):
        assert client.post(f"/receipts/{receipt_id}/confirm", json=bad, headers=alice).status_code == 422
    assert client.get(f"/receipts/{receipt_id}", headers=alice).json()["status"] == "needs_review"


def test_confirm_is_all_or_nothing(client, container, sign_in, engine, monkeypatch):
    alice, alice_id = sign_in()
    receipt_id = upload(client, alice).json()["id"]

    def fail(self, receipt_id, lines):
        raise RuntimeError("disk full")

    # Fail on the last step, after the vendor and the receipt have already been written.
    monkeypatch.setattr(SqlReceiptRepository, "_replace_lines", fail)
    with pytest.raises(RuntimeError):
        client.post(f"/receipts/{receipt_id}/confirm", json=confirm_body(vendor_name="Brand New Vendor"), headers=alice)
    monkeypatch.undo()

    receipt = client.get(f"/receipts/{receipt_id}", headers=alice).json()
    assert receipt["status"] == "needs_review"  # the status change was rolled back
    assert len(receipt["lines"]) == 2  # the draft lines are still there
    with user_scoped_connection(engine, alice_id) as conn:
        assert conn.execute(text("SELECT count(*) FROM vendors")).scalar_one() == 0  # and so was the vendor


def test_a_receipt_still_being_read_cannot_be_confirmed(client, container, sign_in):
    alice, alice_id = sign_in()
    # Upload through the use case only, so the background step has not run yet.
    view = container.receipts.upload(alice_id, UploadReceiptRequest(b"not-read-yet", "image/png"))
    response = client.post(f"/receipts/{view.receipt.id}/confirm", json=confirm_body(), headers=alice)
    assert response.status_code == 409


def test_users_cannot_reach_each_others_receipts(client, alice, sign_in):
    receipt_id = upload(client, alice).json()["id"]
    bob, _ = sign_in()

    assert client.get("/receipts", headers=bob).json() == []
    assert client.get(f"/receipts/{receipt_id}", headers=bob).status_code == 404
    assert client.post(f"/receipts/{receipt_id}/confirm", json=confirm_body(), headers=bob).status_code == 404
    assert client.delete(f"/receipts/{receipt_id}", headers=bob).status_code == 404

    assert client.get(f"/receipts/{receipt_id}", headers=alice).json()["status"] == "needs_review"  # untouched


def test_delete_removes_the_receipt_and_its_file(client, alice, tmp_path):
    receipt_id = upload(client, alice).json()["id"]
    assert [p for p in tmp_path.rglob("*") if p.is_file()]

    assert client.delete(f"/receipts/{receipt_id}", headers=alice).status_code == 204
    assert client.get(f"/receipts/{receipt_id}", headers=alice).status_code == 404
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]
    assert upload(client, alice).status_code == 202  # the same file can be uploaded again


def test_receipt_and_category_endpoints_need_a_token(client):
    assert client.get("/receipts").status_code == 401
    assert client.get("/receipts/1").status_code == 401
    assert client.post("/receipts/manual", json=confirm_body()).status_code == 401
    assert client.delete("/receipts/1").status_code == 401
    assert client.get("/categories").status_code == 401


def test_categories_lists_the_shared_defaults(client, alice):
    categories = client.get("/categories", headers=alice).json()
    assert {"Groceries", "Dining"} <= {c["name"] for c in categories}
    assert all(c["is_shared"] for c in categories)


def test_unstorable_model_output_fails_the_receipt_instead_of_leaving_it_stuck(client, alice, extractor):
    # An amount far beyond what the database column can hold.
    extractor.result = ExtractedReceipt(
        total=Decimal("1e20"), lines=(ExtractedLine(description="x", line_total=Decimal(1)),)
    )
    receipt_id = upload(client, alice).json()["id"]
    assert client.get(f"/receipts/{receipt_id}", headers=alice).json()["status"] == "failed"
    # ...and the user can still enter it by hand.
    assert client.post(f"/receipts/{receipt_id}/confirm", json=confirm_body(), headers=alice).status_code == 200


def test_an_error_while_saving_the_draft_fails_the_receipt_and_is_logged(client, alice, monkeypatch, caplog):
    def fail(self, *args):
        raise RuntimeError("database went away")

    monkeypatch.setattr(SqlReceiptRepository, "save_extraction", fail)
    receipt_id = upload(client, alice).json()["id"]
    monkeypatch.undo()

    assert client.get(f"/receipts/{receipt_id}", headers=alice).json()["status"] == "failed"
    assert "Could not save the draft" in caplog.text
    assert "database went away" in caplog.text


def test_each_failed_extraction_attempt_is_logged(client, alice, extractor, caplog):
    extractor.result = None
    upload(client, alice)
    assert caplog.text.count("Extraction attempt") == 2
    assert "The receipt could not be read" in caplog.text


def test_a_token_for_a_deleted_account_is_refused(client, sign_in, engine):
    headers, user_id = sign_in()
    assert client.get("/receipts", headers=headers).status_code == 200

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})

    assert client.get("/receipts", headers=headers).status_code == 401
    assert upload(client, headers).status_code == 401
    assert client.get("/categories", headers=headers).status_code == 401
