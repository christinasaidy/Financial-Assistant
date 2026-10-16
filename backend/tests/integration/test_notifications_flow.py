"""Notifications through the real API and database. The examples and their outcomes were approved by the
user on 2026-10-14, before this code was written. Do not change an expected value to make a test pass."""

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

TWELFTH = date(2026, 10, 12)
READABLE = ExtractedReceipt(
    vendor_name="Spinneys",
    receipt_date=date(2026, 10, 11),
    currency="USD",
    total=Decimal("5.00"),
    lines=(ExtractedLine(description="LABAN", line_total=Decimal("5.00")),),
)


@pytest.fixture
def settings(engine):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    return settings


@pytest.fixture
def extractor():
    return FakeReceiptExtractor(READABLE)


@pytest.fixture
def client_on(settings, extractor, tmp_path):
    def _client_on(today: date) -> TestClient:
        container = build_container(
            settings, extractor=extractor, storage=LocalFileStorage(tmp_path), today=lambda: today
        )
        return TestClient(create_app(container))

    return _client_on


@pytest.fixture
def client(client_on):
    return client_on(TWELFTH)


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
def groceries(client, alice):
    return next(c["id"] for c in client.get("/categories", headers=alice).json() if c["name"] == "Groceries")


def add(client, headers, total, category, day="2026-10-05"):
    body = {"receipt_date": day, "currency": "USD", "total": total, "primary_category_id": category}
    response = client.post("/receipts/manual", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def set_budget(client, headers, category, limit, month="2026-10"):
    response = client.put(f"/budgets/{category}", json={"month": month, "limit_amount": limit}, headers=headers)
    assert response.status_code == 200, response.text


def notifications(client, headers) -> list[dict]:
    response = client.get("/notifications", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def budget_kinds(client, headers) -> list[str]:
    """Budget notification kinds, oldest first."""
    kinds = [n["kind"] for n in notifications(client, headers) if n["kind"].startswith(("budget", "pace"))]
    return list(reversed(kinds))


# --- Example 1: Groceries in October, budget $400, today 12 October ---


def test_example_1_near_once_then_limit_reached(client, alice, groceries):
    set_budget(client, alice, groceries, "400")
    add(client, alice, "330", groceries)  # 83%
    assert budget_kinds(client, alice) == ["budget_near"]
    assert notifications(client, alice)[0]["body"] == "Groceries: you've used 83% of your $400 budget."

    add(client, alice, "20", groceries)  # 88%: near was already sent
    assert budget_kinds(client, alice) == ["budget_near"]

    add(client, alice, "60", groceries)  # 103%
    assert budget_kinds(client, alice) == ["budget_near", "budget_limit_reached"]
    latest = notifications(client, alice)[0]
    assert latest["body"] == "Groceries: you've reached your $400 budget ($10 over)."
    assert latest["data"] == {"category_id": groceries, "month": "2026-10"}


# --- Example 2: a big jump gives only "limit reached" ---


def test_example_2_a_jump_past_the_limit_skips_near(client, alice, groceries):
    set_budget(client, alice, groceries, "400")
    add(client, alice, "300", groceries)
    add(client, alice, "120", groceries)  # $300 -> $420
    assert "budget_near" not in budget_kinds(client, alice)
    assert budget_kinds(client, alice)[-1] == "budget_limit_reached"


# --- Example 3: pace ---


def test_example_3_pace_warning_on_12_october(client, alice, groceries):
    set_budget(client, alice, groceries, "400")
    add(client, alice, "200", groceries)
    assert budget_kinds(client, alice) == ["pace_warning"]
    assert notifications(client, alice)[0]["body"] == (
        "At this pace you'll spend about $517 on Groceries this month (budget $400)."
    )


def test_example_3_no_pace_warning_on_5_october(client_on, alice, groceries):
    fifth = client_on(date(2026, 10, 5))
    set_budget(fifth, alice, groceries, "400")
    add(fifth, alice, "200", groceries)
    assert budget_kinds(fifth, alice) == []


# --- Example 4: what does and does not notify ---


def test_example_4_a_past_month_never_notifies(client, alice, groceries):
    set_budget(client, alice, groceries, "100", month="2026-09")
    add(client, alice, "150", groceries, day="2026-09-20")  # September is over its budget
    assert all(n["data"].get("month") != "2026-09" for n in notifications(client, alice))


def test_example_4_lowering_a_budget_below_what_is_spent_notifies(client, alice, groceries):
    set_budget(client, alice, groceries, "400")
    add(client, alice, "310", groceries)
    set_budget(client, alice, groceries, "300")
    assert budget_kinds(client, alice)[-1] == "budget_limit_reached"


# --- No repeats in the same month ---


def test_dropping_back_under_and_crossing_again_does_not_repeat(client, alice, groceries):
    set_budget(client, alice, groceries, "400")
    receipt = add(client, alice, "330", groceries)
    assert client.delete(f"/receipts/{receipt}", headers=alice).status_code == 204  # back to $0
    add(client, alice, "335", groceries)  # crosses 80% again
    assert budget_kinds(client, alice).count("budget_near") == 1


# --- Receipt notifications ---


def test_a_read_receipt_says_it_is_ready(client, alice):
    receipt_id = client.post("/receipts", files={"file": ("r", b"img", "image/jpeg")}, headers=alice).json()["id"]
    ready = [n for n in notifications(client, alice) if n["kind"] == "receipt_ready"]
    assert len(ready) == 1
    assert ready[0]["body"] == "Your Spinneys receipt is ready to review."
    assert ready[0]["data"] == {"receipt_id": receipt_id}


def test_an_unreadable_receipt_says_so(client, alice, extractor):
    extractor.result = None
    receipt = client.post("/receipts", files={"file": ("r", b"img", "image/jpeg")}, headers=alice).json()
    uploaded = date.fromisoformat(client.get(f"/receipts/{receipt['id']}", headers=alice).json()["created_at"][:10])
    failed = [n for n in notifications(client, alice) if n["kind"] == "receipt_failed"]
    assert len(failed) == 1
    expected = f"We couldn't read your receipt from {uploaded.day} {uploaded:%b}. You can enter it by hand."
    assert failed[0]["body"] == expected
    assert failed[0]["data"] == {"receipt_id": receipt["id"]}


# --- The list ---


def test_unread_count_and_marking_as_read(client, alice):
    for content in (b"one", b"two"):
        client.post("/receipts", files={"file": ("r", content, "image/jpeg")}, headers=alice)
    items = notifications(client, alice)
    assert client.get("/notifications/unread-count", headers=alice).json() == {"unread_count": 2}
    assert all(not n["read"] for n in items)

    assert client.post(f"/notifications/{items[0]['id']}/read", headers=alice).status_code == 204
    assert client.get("/notifications", headers=alice).json()["unread_count"] == 1

    assert client.post("/notifications/read-all", headers=alice).status_code == 204
    assert client.get("/notifications/unread-count", headers=alice).json() == {"unread_count": 0}
    assert all(n["read"] for n in notifications(client, alice))


def test_newest_first(client, alice):
    for content in (b"first", b"second"):
        client.post("/receipts", files={"file": ("r", content, "image/jpeg")}, headers=alice)
    first, second = sorted(n["data"]["receipt_id"] for n in notifications(client, alice))
    assert [n["data"]["receipt_id"] for n in notifications(client, alice)] == [second, first]


def test_users_only_see_and_mark_their_own(client, alice, sign_in):
    client.post("/receipts", files={"file": ("r", b"img", "image/jpeg")}, headers=alice)
    alices = notifications(client, alice)[0]["id"]
    bob = sign_in()
    assert notifications(client, bob) == []
    assert client.post(f"/notifications/{alices}/read", headers=bob).status_code == 404
    assert notifications(client, alice)[0]["read"] is False  # untouched
    assert client.post("/notifications/999999999/read", headers=alice).status_code == 404


def test_notification_endpoints_need_a_token(client):
    assert client.get("/notifications").status_code == 401
    assert client.get("/notifications/unread-count").status_code == 401
    assert client.post("/notifications/1/read").status_code == 401
    assert client.post("/notifications/read-all").status_code == 401


def test_a_future_dated_receipt_does_not_cause_a_pace_warning(client, alice, groceries):
    # On 12 October: $100 dated the 5th is on pace for $258; a misdated $200 on the 25th must not change that.
    set_budget(client, alice, groceries, "400")
    add(client, alice, "100", groceries, day="2026-10-05")
    add(client, alice, "200", groceries, day="2026-10-25")
    assert budget_kinds(client, alice) == []  # 75% is under "near", and pace up to today is under the limit
