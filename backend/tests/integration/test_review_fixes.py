"""Code review (2026-10-15) findings 2, 4 and 11, checked through the real API and database."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt
from app.infrastructure.config import Settings
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


@pytest.fixture
def client(engine, tmp_path):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    container = build_container(settings, extractor=FakeReceiptExtractor(SPINNEYS), storage=LocalFileStorage(tmp_path))
    return TestClient(create_app(container))


@pytest.fixture
def alice(client, engine):
    email = f"{uuid.uuid4()}@test.local"
    body = {"email": email, "password": "correct-horse"}
    assert client.post("/auth/register", json=body).status_code == 201
    yield {"Authorization": "Bearer " + client.post("/auth/login", json=body).json()["access_token"]}
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


def manual(client, headers, **overrides):
    body = {"receipt_date": "2026-10-15", "currency": "USD", "total": "1.50", **overrides}
    return client.post("/receipts/manual", json=body, headers=headers)


def groceries(client, headers):
    return next(c["id"] for c in client.get("/categories", headers=headers).json() if c["name"] == "Groceries")


# --- Finding 2: too many decimals are refused with a clear 422, never a database error ---


@pytest.mark.parametrize(
    "overrides",
    [
        {"total": "1.005"},
        {"lines": [{"description": "milk", "line_total": "1.50", "quantity": "0.0001"}]},
        {"lines": [{"description": "milk", "line_total": "1.505"}]},
        {"lbp_per_usd": "0.0000001"},
        {"total": "NaN"},
    ],
)
def test_typed_values_with_too_many_decimals_get_a_clear_422(client, alice, overrides):
    response = manual(client, alice, **overrides)
    assert response.status_code == 422, response.text


def test_a_budget_of_0_001_gets_a_clear_422(client, alice):
    body = {"month": "2026-10", "limit_amount": "0.001"}
    assert client.put(f"/budgets/{groceries(client, alice)}", json=body, headers=alice).status_code == 422


def test_accepted_values_come_back_exactly(client, alice):
    lines = [{"description": "milk", "line_total": "1.50", "quantity": "0.75", "unit_price": "2.00"}]
    receipt = manual(client, alice, lines=lines, lbp_per_usd="89500.123456").json()
    assert (receipt["total"], receipt["lbp_per_usd"]) == ("1.50", "89500.123456")
    line = receipt["lines"][0]
    assert (line["line_total"], line["quantity"], line["unit_price"]) == ("1.50", "0.750", "2.00")


# --- Finding 4: a vendor the user cleared stays cleared ---


def test_clearing_the_extracted_vendor_sticks(client, alice):
    receipt_id = client.post("/receipts", files={"file": ("r", b"img", "image/png")}, headers=alice).json()["id"]
    assert client.get(f"/receipts/{receipt_id}", headers=alice).json()["vendor_name"] == "Spinneys"  # draft

    body = {"vendor_name": None, "receipt_date": "2026-10-15", "currency": "USD", "total": "9.37"}
    confirmed = client.post(f"/receipts/{receipt_id}/confirm", json=body, headers=alice).json()
    assert confirmed["vendor_name"] is None
    assert "missing_vendor" in confirmed["flags"]
    assert client.get(f"/receipts/{receipt_id}", headers=alice).json()["vendor_name"] is None


def test_clearing_the_vendor_in_a_later_correction_sticks(client, alice):
    receipt_id = manual(client, alice, vendor_name="Spinneys").json()["id"]
    body = {"vendor_name": "", "receipt_date": "2026-10-15", "currency": "USD", "total": "1.50"}
    client.post(f"/receipts/{receipt_id}/confirm", json=body, headers=alice)
    assert client.get(f"/receipts/{receipt_id}", headers=alice).json()["vendor_name"] is None


# --- Finding 11: months that cannot be represented are refused ---


@pytest.mark.parametrize("month", ["0000-01", "9999-12"])
def test_impossible_months_are_refused_not_crashed(client, alice, month):
    assert client.get("/spending/summary", params={"month": month}, headers=alice).status_code == 422
    assert client.get("/budgets", params={"month": month}, headers=alice).status_code == 422
    body = {"month": month, "limit_amount": "100"}
    assert client.put(f"/budgets/{groceries(client, alice)}", json=body, headers=alice).status_code == 422


@pytest.mark.parametrize("month", ["2026-12", "2027-01", "2028-02"])
def test_ordinary_december_january_and_leap_months_work(client, alice, month):
    assert client.get("/spending/summary", params={"month": month}, headers=alice).status_code == 200
    assert client.get("/budgets", params={"month": month}, headers=alice).status_code == 200
