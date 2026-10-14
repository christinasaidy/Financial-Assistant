"""Spending through the real API and database. Example 1 is the October month the user approved."""

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

# What the fake vision model returns: a receipt that will sit in "waiting for review".
WAITING = ExtractedReceipt(
    vendor_name="Spinneys",
    receipt_date=date(2026, 10, 20),
    currency="USD",
    total=Decimal("40.00"),
    lines=(ExtractedLine(description="TOMATOES", line_total=Decimal("40.00")),),
)


@pytest.fixture
def settings(engine):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    return settings


@pytest.fixture
def client(settings, tmp_path):
    container = build_container(settings, extractor=FakeReceiptExtractor(WAITING), storage=LocalFileStorage(tmp_path))
    return TestClient(create_app(container))


@pytest.fixture
def sign_in(client, engine):
    emails: list[str] = []

    def _sign_in() -> dict[str, str]:
        email = f"{uuid.uuid4()}@test.local"
        emails.append(email)
        body = {"email": email, "password": "correct-horse"}
        assert client.post("/auth/register", json=body).status_code == 201
        token = client.post("/auth/login", json=body).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    yield _sign_in
    with engine.begin() as conn:
        for email in emails:
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


@pytest.fixture
def alice(sign_in):
    return sign_in()


def category_ids(client, headers) -> dict[str, int]:
    return {c["name"]: c["id"] for c in client.get("/categories", headers=headers).json()}


def add(client, headers, day, total, currency="USD", category=None, lines=(), rate=None):
    body = {
        "vendor_name": "shop",
        "receipt_date": day,
        "currency": currency,
        "total": total,
        "primary_category_id": category,
        "lines": [{"description": name, "line_total": amount, "category_id": cat} for name, amount, cat in lines],
    }
    if rate is not None:
        body["lbp_per_usd"] = rate
    response = client.post("/receipts/manual", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def summary(client, headers, **params):
    response = client.get("/spending/summary", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def amounts(section) -> dict[str, str]:
    return {item["name"]: item["amount"] for item in section["categories"]}


def test_example_1_october_through_the_api(client, alice):
    ids = category_ids(client, alice)
    g, h, d = ids["Groceries"], ids["Household"], ids["Dining"]
    add(client, alice, "2026-10-03", "23.00", lines=[("Milk", "5", g), ("Bread", "3", g), ("Detergent", "12", h)])
    add(client, alice, "2026-10-10", "15.00", category=d)
    add(client, alice, "2026-10-12", "8.50")
    assert client.post(  # read by the (fake) model, then left waiting for review
        "/receipts", files={"file": ("r", b"img", "image/jpeg")}, headers=alice
    ).status_code == 202
    add(client, alice, "2026-09-30", "10.00", category=g)  # printed in September, scanned in October

    october = summary(client, alice, month="2026-10")
    combined = october["combined"]
    assert combined["currency"] == "USD"
    assert combined["total"] == "46.50"
    assert amounts(combined) == {"Dining": "15.00", "Household": "12.00", "Uncategorized": "8.50", "Groceries": "8.00"}
    assert [item["name"] for item in combined["categories"]] == ["Dining", "Household", "Uncategorized", "Groceries"]
    assert combined["adjustments"] == "3.00"
    assert combined["receipt_count"] == 3
    assert october["awaiting_review"] == 1
    assert [section["currency"] for section in october["by_currency"]] == ["USD"]

    september = summary(client, alice, month="2026-09")["combined"]
    assert (september["total"], amounts(september)) == ("10.00", {"Groceries": "10.00"})


def test_example_2_november_through_the_api(client, alice):
    ids = category_ids(client, alice)
    lines = [("Laban", "4", None), ("Chips", "6", None), ("Shampoo", "10", ids["Health"])]
    add(client, alice, "2026-11-05", "18.80", category=ids["Groceries"], lines=lines)

    november = summary(client, alice, month="2026-11")["combined"]
    assert amounts(november) == {"Groceries": "10.00", "Health": "10.00"}
    assert november["adjustments"] == "-1.20"
    assert november["total"] == "18.80"


def test_example_3_december_through_the_api(client, alice):
    ids = category_ids(client, alice)
    add(client, alice, "2026-12-02", "450000", currency="LBP", category=ids["Groceries"], rate="89500")
    add(client, alice, "2026-12-03", "12.00", category=ids["Dining"], rate="89500")
    lines = [("Rice", "900000", ids["Groceries"]), ("Oil", "250000", None)]
    add(client, alice, "2026-12-04", "1200000", currency="LBP", lines=lines, rate="89500")

    december = summary(client, alice, month="2026-12")
    usd, lbp = december["by_currency"]
    assert (usd["currency"], usd["total"], amounts(usd)) == ("USD", "12.00", {"Dining": "12.00"})
    assert (lbp["currency"], lbp["total"], lbp["adjustments"]) == ("LBP", "1650000.00", "50000.00")
    assert amounts(lbp) == {"Groceries": "1350000.00", "Uncategorized": "250000.00"}

    combined = december["combined"]
    assert (combined["total"], combined["adjustments"]) == ("30.44", "0.57")
    assert amounts(combined) == {"Groceries": "15.08", "Dining": "12.00", "Uncategorized": "2.79"}
    assert december["converted_at_current_rate"] == 0

    in_lbp = summary(client, alice, month="2026-12", currency="LBP")["combined"]
    assert in_lbp["total"] == "2724000.00"


def test_confirming_saves_the_rate_and_corrections_keep_it(client, alice, settings):
    receipt = add(client, alice, "2026-10-01", "150000", currency="LBP")
    assert Decimal(receipt["lbp_per_usd"]) == settings.default_lbp_per_usd  # today's default

    own_rate = add(client, alice, "2026-10-02", "150000", currency="LBP", rate="15000")
    assert Decimal(own_rate["lbp_per_usd"]) == 15000

    body = {"receipt_date": "2026-10-02", "currency": "LBP", "total": "300000"}  # a correction, no rate given
    corrected = client.post(f"/receipts/{own_rate['id']}/confirm", json=body, headers=alice).json()
    assert Decimal(corrected["lbp_per_usd"]) == 15000  # the original rate is kept


def test_an_old_receipt_is_converted_at_its_own_rate(client, alice):
    add(client, alice, "2026-10-01", "150000", currency="LBP", category=None, rate="15000")
    assert summary(client, alice, month="2026-10")["combined"]["total"] == "10.00"


@pytest.mark.parametrize("bad_rate", ["0", "-5"])
def test_impossible_rates_are_refused(client, alice, bad_rate):
    body = {"receipt_date": "2026-10-01", "currency": "LBP", "total": "1000", "lbp_per_usd": bad_rate}
    assert client.post("/receipts/manual", json=body, headers=alice).status_code == 422


def test_users_only_see_their_own_spending(client, alice, sign_in):
    add(client, alice, "2026-10-03", "23.00")
    bob = sign_in()
    october = summary(client, bob, month="2026-10")
    assert october["combined"]["total"] == "0.00"
    assert october["combined"]["categories"] == []
    assert october["by_currency"] == []


def test_bad_parameters_and_missing_token(client, alice):
    for params in ({"month": "2026-13"}, {"month": "october"}, {"month": "2026-1"}, {"currency": "EUR"}):
        assert client.get("/spending/summary", params=params, headers=alice).status_code == 422
    assert client.get("/spending/summary").status_code == 401
    assert client.get("/spending/summary", headers=alice).status_code == 200  # defaults to this month
