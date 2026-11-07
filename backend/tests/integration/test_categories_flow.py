"""Private categories through the real API and database. The worked examples were approved by the user on
2026-11-07, before this code was written. Do not change an expected value to make a test pass."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.domain.categories.errors import CategoryAlreadyExists
from app.infrastructure.config import Settings
from app.infrastructure.database.unit_of_work import SqlUnitOfWorkFactory
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_container
from tests.fakes import FakeReceiptExtractor

SHARED = ["Groceries", "Dining", "Transport", "Utilities", "Health", "Shopping", "Entertainment", "Household"]


@pytest.fixture
def client(engine, tmp_path):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    return TestClient(create_app(build_container(settings, extractor=FakeReceiptExtractor(),
                                                 storage=LocalFileStorage(tmp_path))))  # fmt: skip


@pytest.fixture
def sign_in(client, engine):
    emails: list[str] = []

    def _sign_in() -> dict[str, str]:
        email = f"{uuid.uuid4()}@test.local"
        emails.append(email)
        body = {"email": email, "password": "correct-horse"}
        assert client.post("/auth/register", json=body).status_code == 201
        return {"Authorization": f"Bearer {client.post('/auth/login', json=body).json()['access_token']}"}

    yield _sign_in
    with engine.begin() as conn:
        for email in emails:
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


def create(client, headers, name):
    return client.post("/categories", json={"name": name}, headers=headers)


def names(client, headers):
    return [c["name"] for c in client.get("/categories", headers=headers).json()]


def test_a_new_category_is_private_and_listed_after_the_shared_ones(client, sign_in):
    alice = sign_in()
    response = create(client, alice, "Pets")
    assert response.status_code == 201
    body = response.json()
    assert (body["name"], body["is_shared"]) == ("Pets", False)
    assert isinstance(body["id"], int)
    listed = names(client, alice)
    assert sorted(listed[:8]) == sorted(SHARED) and listed[8:] == ["Pets"]


def test_spaces_are_tidied(client, sign_in):
    assert create(client, sign_in(), "  Home   Office ").json()["name"] == "Home Office"


@pytest.mark.parametrize(("first", "second"), [("Pets", "pets"), ("Pets", "  PETS ")])
def test_the_same_name_twice_is_a_conflict(client, sign_in, first, second):
    alice = sign_in()
    assert create(client, alice, first).status_code == 201
    assert create(client, alice, second).status_code == 409


@pytest.mark.parametrize("name", ["groceries", "Household", "uncategorized", "Tax, discounts & rounding"])
def test_a_shared_or_assistant_name_is_a_conflict(client, sign_in, name):
    alice = sign_in()
    assert create(client, alice, name).status_code == 409
    assert len(names(client, alice)) == 8  # nothing was added


@pytest.mark.parametrize(("name", "code"), [("", 422), ("   ", 422), ("x" * 41, 422), ("x" * 40, 201)])
def test_blank_or_long_names(client, sign_in, name, code):
    assert create(client, sign_in(), name).status_code == code


def test_at_most_50_private_categories(client, sign_in):
    alice = sign_in()
    for number in range(50):
        assert create(client, alice, f"Category {number}").status_code == 201
    assert create(client, alice, "One too many").status_code == 422
    assert len(names(client, alice)) == 58


def test_another_users_category_is_neither_seen_nor_usable(client, sign_in):
    alice, bob = sign_in(), sign_in()
    pets = create(client, alice, "Pets").json()["id"]
    assert "Pets" not in names(client, bob)
    receipt = {"vendor_name": "Petzone", "receipt_date": "2026-11-01", "currency": "USD", "total": "10.00",
               "primary_category_id": pets, "lines": [], "lbp_per_usd": "89500"}  # fmt: skip
    refused = client.post("/receipts/manual", json=receipt, headers=bob)
    assert (refused.status_code, refused.json()["detail"]) == (422, "Unknown category")
    assert create(client, bob, "Pets").status_code == 201  # his own, separate from Alice's
    assert create(client, alice, "Pets").status_code == 409  # Alice's is still hers alone


def test_a_new_category_can_be_used_on_a_receipt(client, sign_in):
    alice = sign_in()
    pets = create(client, alice, "Pets").json()["id"]
    receipt = {"vendor_name": "Petzone", "receipt_date": "2026-11-01", "currency": "USD", "total": "10.00",
               "primary_category_id": pets, "lines": [], "lbp_per_usd": "89500"}  # fmt: skip
    assert client.post("/receipts/manual", json=receipt, headers=alice).status_code == 201


def test_signing_in_is_required(client):
    assert client.post("/categories", json={"name": "Pets"}).status_code == 401


def test_a_duplicate_that_gets_past_the_service_is_stopped_by_the_database(engine, sign_in, client):
    """Two requests at once could both pass the service's check; the unique index then stops the second."""
    alice = sign_in()
    alice_id = client.get("/auth/me", headers=alice).json()["id"]
    uow = SqlUnitOfWorkFactory(engine)
    with uow(alice_id) as work:
        work.categories.add("Pets")
    with pytest.raises(CategoryAlreadyExists), uow(alice_id) as work:
        work.categories.add("pets")  # straight to the database, no service check
    assert names(client, alice).count("Pets") == 1
