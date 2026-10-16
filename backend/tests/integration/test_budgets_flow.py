"""Budgets through the real API and database. Examples 1-4 and their expected numbers were approved by
the user on 2026-10-14, before this code was written. Do not change an expected value to make a test pass."""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import user_scoped_connection
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeReceiptExtractor


@pytest.fixture
def settings(engine):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    return settings


@pytest.fixture
def client_on(settings, tmp_path):
    """A client whose idea of "today" is fixed, so pace can be tested."""

    def _client_on(today: date) -> TestClient:
        container = build_container(
            settings, extractor=FakeReceiptExtractor(), storage=LocalFileStorage(tmp_path), today=lambda: today
        )
        return TestClient(create_app(container))

    return _client_on


@pytest.fixture
def client(client_on):
    return client_on(date(2026, 10, 10))


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


@pytest.fixture
def ids(client, alice):
    return {c["name"]: c["id"] for c in client.get("/categories", headers=alice).json()}


def add(client, headers, day, total, currency="USD", category=None, lines=(), rate="89500"):
    body = {
        "receipt_date": day,
        "currency": currency,
        "total": total,
        "primary_category_id": category,
        "lines": [{"description": name, "line_total": amount, "category_id": cat} for name, amount, cat in lines],
        "lbp_per_usd": rate,
    }
    response = client.post("/receipts/manual", json=body, headers=headers)
    assert response.status_code == 201, response.text


def set_budget(client, headers, category_id, month, limit, currency="USD"):
    response = client.put(
        f"/budgets/{category_id}", json={"month": month, "currency": currency, "limit_amount": limit}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def budgets(client, headers, month) -> dict[str, dict]:
    response = client.get("/budgets", params={"month": month}, headers=headers)
    assert response.status_code == 200, response.text
    return {item["category_name"]: item for item in response.json()}


# --- Example 1: Groceries on 10 October. Approved: spent $200, remaining $200, 50%, ok, pace $620 ---


def test_example_1_groceries_on_10_october(client, alice, ids):
    g = ids["Groceries"]
    set_budget(client, alice, g, "2026-10", "400")
    add(client, alice, "2026-10-02", "153.00", lines=[("Groceries", "150.00", g)])  # +$3 tax, not counted
    add(client, alice, "2026-10-05", "4475000", currency="LBP", category=g)  # $50 at 89,500
    add(client, alice, "2026-10-06", "20.00", category=ids["Dining"])  # another category, not counted

    groceries = budgets(client, alice, "2026-10")["Groceries"]
    assert groceries["spent"] == "200.00"
    assert groceries["remaining"] == "200.00"
    assert groceries["percent_used"] == "50.0"
    assert groceries["state"] == "ok"
    assert groceries["pace"] == {"projected": "620.00", "low_confidence": False, "projected_over": True}


# --- Example 2: Dining on 3 October. Approved: spent $30, pace $310, low-confidence ---


def test_example_2_dining_on_3_october(client_on, alice, ids):
    client = client_on(date(2026, 10, 3))
    set_budget(client, alice, ids["Dining"], "2026-10", "100")
    add(client, alice, "2026-10-02", "30.00", category=ids["Dining"])

    dining = budgets(client, alice, "2026-10")["Dining"]
    assert dining["spent"] == "30.00"
    assert dining["pace"] == {"projected": "310.00", "low_confidence": True, "projected_over": True}


# --- Example 3: Household, budget $50. Approved: $45 near (90%), $50 limit reached, $60 limit reached (-$10) ---


def test_example_3_household(client, alice, ids):
    h = ids["Household"]
    set_budget(client, alice, h, "2026-10", "50")

    add(client, alice, "2026-10-01", "45.00", category=h)
    household = budgets(client, alice, "2026-10")["Household"]
    assert (household["percent_used"], household["state"]) == ("90.0", "near")

    add(client, alice, "2026-10-02", "5.00", category=h)
    household = budgets(client, alice, "2026-10")["Household"]
    assert (household["spent"], household["remaining"], household["state"]) == ("50.00", "0.00", "limit_reached")

    add(client, alice, "2026-10-03", "10.00", category=h)
    household = budgets(client, alice, "2026-10")["Household"]
    assert (household["remaining"], household["percent_used"], household["state"]) == (
        "-10.00",
        "120.0",
        "limit_reached",
    )


# --- Example 4: a budget repeats. Approved: Oct 400, Nov 400, Dec 350, Jan 350, Sep none ---


def test_example_4_a_budget_repeats_until_changed(client, alice, ids):
    g = ids["Groceries"]
    set_budget(client, alice, g, "2026-10", "400")
    set_budget(client, alice, g, "2026-12", "350")

    assert budgets(client, alice, "2026-09") == {}
    assert budgets(client, alice, "2026-10")["Groceries"]["limit_amount"] == "400.00"
    november = budgets(client, alice, "2026-11")["Groceries"]
    assert (november["limit_amount"], november["set_in"]) == ("400.00", "2026-10-01")
    assert budgets(client, alice, "2026-12")["Groceries"]["limit_amount"] == "350.00"
    assert budgets(client, alice, "2027-01")["Groceries"]["limit_amount"] == "350.00"


# --- The rest of the agreed rules ---


def test_unconfirmed_receipts_do_not_count(client, alice, ids):
    set_budget(client, alice, ids["Groceries"], "2026-10", "400")
    client.post("/receipts", files={"file": ("r", b"img", "image/jpeg")}, headers=alice)  # ends "failed"
    body = {"receipt_date": "2026-10-01", "currency": "USD", "total": "99", "primary_category_id": ids["Groceries"]}
    upload_id = client.get("/receipts", headers=alice).json()[0]["id"]
    assert client.get(f"/receipts/{upload_id}", headers=alice).json()["status"] == "failed"
    assert budgets(client, alice, "2026-10")["Groceries"]["spent"] == "0.00"
    client.post(f"/receipts/{upload_id}/confirm", json=body, headers=alice)  # once confirmed, it counts
    assert budgets(client, alice, "2026-10")["Groceries"]["spent"] == "99.00"


def test_pace_is_only_for_the_current_month(client_on, alice, ids):
    october = client_on(date(2026, 11, 15))  # October is now in the past
    set_budget(october, alice, ids["Groceries"], "2026-10", "400")
    assert budgets(october, alice, "2026-10")["Groceries"]["pace"] is None
    assert budgets(october, alice, "2026-12")["Groceries"]["pace"] is None  # the future
    assert budgets(october, alice, "2026-11")["Groceries"]["pace"] is not None  # this month


def test_a_budget_in_lbp_counts_dollar_spending_too(client, alice, ids):
    g = ids["Groceries"]
    set_budget(client, alice, g, "2026-10", "8950000", currency="LBP")  # = $100 at 89,500
    add(client, alice, "2026-10-01", "50.00", category=g)  # $50 = 4,475,000 LBP
    groceries = budgets(client, alice, "2026-10")["Groceries"]
    assert (groceries["currency"], groceries["spent"], groceries["percent_used"]) == ("LBP", "4475000.00", "50.0")


def test_setting_again_for_the_same_month_replaces_the_amount(client, alice, ids):
    set_budget(client, alice, ids["Groceries"], "2026-10", "400")
    replaced = set_budget(client, alice, ids["Groceries"], "2026-10", "300")
    assert replaced["limit_amount"] == "300.00"
    assert len(budgets(client, alice, "2026-10")) == 1


def test_invalid_budgets_are_refused(client, alice, ids, sign_in):
    g = ids["Groceries"]
    for body in (
        {"month": "2026-10", "limit_amount": "0"},
        {"month": "2026-10", "limit_amount": "-5"},
        {"month": "2026-13", "limit_amount": "100"},
        {"month": "2026-10", "limit_amount": "100", "currency": "EUR"},
    ):
        assert client.put(f"/budgets/{g}", json=body, headers=alice).status_code == 422
    good = {"month": "2026-10", "limit_amount": "100"}
    assert client.put("/budgets/999999999", json=good, headers=alice).status_code == 422  # no such category


def test_another_users_private_category_cannot_get_a_budget(client, alice, sign_in, engine):
    bob = sign_in()
    alice_id = client.get("/auth/me", headers=alice).json()["id"]
    with user_scoped_connection(engine, alice_id) as conn:  # a private category owned by alice
        private = conn.execute(
            text("INSERT INTO categories (user_id, name) VALUES (app_user_id(), 'Alice only') RETURNING id")
        ).scalar_one()
    good = {"month": "2026-10", "limit_amount": "100"}
    assert client.put(f"/budgets/{private}", json=good, headers=bob).status_code == 422


def test_users_only_see_and_delete_their_own_budgets(client, alice, ids, sign_in):
    set_budget(client, alice, ids["Groceries"], "2026-10", "400")
    bob = sign_in()
    assert budgets(client, bob, "2026-10") == {}
    assert client.delete(f"/budgets/{ids['Groceries']}", headers=bob).status_code == 404
    assert "Groceries" in budgets(client, alice, "2026-10")  # untouched


def test_deleting_removes_the_budget_for_every_month(client, alice, ids):
    g = ids["Groceries"]
    set_budget(client, alice, g, "2026-10", "400")
    set_budget(client, alice, g, "2026-12", "350")
    assert client.delete(f"/budgets/{g}", headers=alice).status_code == 204
    assert budgets(client, alice, "2026-10") == {}
    assert budgets(client, alice, "2027-01") == {}
    assert client.delete(f"/budgets/{g}", headers=alice).status_code == 404


def test_budget_endpoints_need_a_token(client):
    assert client.get("/budgets").status_code == 401
    assert client.put("/budgets/1", json={"month": "2026-10", "limit_amount": "1"}).status_code == 401
    assert client.delete("/budgets/1").status_code == 401


# --- Pace counts only spending dated up to today (code review finding 14, agreed 2026-10-16) ---


def test_pace_ignores_receipts_dated_after_today(client_on, alice, ids):
    # The example from 2026-10-16: on 10 October, $100 dated the 5th and $200 dated the 25th.
    client = client_on(date(2026, 10, 10))
    g = ids["Groceries"]
    set_budget(client, alice, g, "2026-10", "400")
    add(client, alice, "2026-10-05", "100.00", category=g)
    add(client, alice, "2026-10-25", "200.00", category=g)

    groceries = budgets(client, alice, "2026-10")["Groceries"]
    assert groceries["spent"] == "300.00"  # the month still counts every receipt
    assert groceries["pace"] == {"projected": "310.00", "low_confidence": False, "projected_over": False}
