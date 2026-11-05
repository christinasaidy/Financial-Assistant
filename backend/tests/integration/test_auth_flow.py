"""Auth against the real database: the SQL repository and the full API wiring from app.main."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.domain.receipts.extraction import ExtractedLine, ExtractedReceipt
from app.domain.users.errors import EmailAlreadyRegistered, InvalidToken
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import user_scoped_connection
from app.infrastructure.database.user_repository import SqlUserRepository
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import build_app, build_container
from tests.fakes import FakeReceiptExtractor


@pytest.fixture
def email(engine):
    address = f"{uuid.uuid4()}@test.local"
    yield address
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE lower(email) = lower(:e)"), {"e": address})


def test_repository_round_trip_and_duplicate_detection(engine, email):
    repo = SqlUserRepository(engine)
    user = repo.add(email, "some-hash")
    assert repo.get_by_id(user.id) == user
    stored = repo.get_credentials_by_email(email.upper())
    assert stored is not None and stored.user == user and stored.password_hash == "some-hash"
    with pytest.raises(EmailAlreadyRegistered):
        repo.add(email.upper(), "other-hash")
    assert repo.get_credentials_by_email("nobody@test.local") is None
    assert repo.get_by_id(-1) is None


def test_full_flow_through_the_real_app(engine, email):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    client = TestClient(build_app(settings))

    assert client.post("/auth/register", json={"email": email, "password": "correct-horse"}).status_code == 201
    assert client.post("/auth/register", json={"email": email, "password": "correct-horse"}).status_code == 409
    assert client.post("/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401

    token = client.post("/auth/login", json={"email": email, "password": "correct-horse"}).json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == email

    # The stored value is an Argon2 hash, never the password.
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT password_hash FROM users WHERE email = :e"), {"e": email}).scalar_one()
    assert stored.startswith("$argon2") and "correct-horse" not in stored


def test_user_scope_sets_the_rls_user_and_does_not_leak(engine, make_user):
    user_id = make_user()
    with user_scoped_connection(engine, user_id) as conn:
        assert conn.execute(text("SELECT app_user_id()")).scalar_one() == user_id
    # A later transaction on the (pooled) connection must start with no user.
    with engine.connect() as conn:
        assert conn.execute(text("SELECT app_user_id()")).scalar_one() is None


# --- Deleting an account (no endpoint yet; approved by the user on 2026-11-05) ---


def test_deleting_an_account_removes_its_rows_and_files_and_nothing_of_others(engine, tmp_path):
    settings = Settings()
    if not settings.jwt_secret:
        pytest.skip("JWT_SECRET is not set")
    read = ExtractedReceipt(vendor_name="Spinneys", receipt_date=date(2026, 11, 1), currency="USD",
                            total=Decimal("2.00"), lines=[ExtractedLine("LABAN", Decimal("2.00"))])  # fmt: skip
    container = build_container(settings, extractor=FakeReceiptExtractor(read), storage=LocalFileStorage(tmp_path))
    client = TestClient(create_app(container))
    emails = [f"{uuid.uuid4()}@test.local" for _ in range(2)]
    try:
        people = []
        for address in emails:
            body = {"email": address, "password": "correct-horse"}
            assert client.post("/auth/register", json=body).status_code == 201
            login = client.post("/auth/login", json=body).json()
            headers = {"Authorization": f"Bearer {login['access_token']}"}
            upload = client.post("/receipts", files={"file": ("r", uuid.uuid4().bytes, "image/jpeg")}, headers=headers)
            assert upload.status_code in (201, 202), upload.text
            manual = {"receipt_date": "2026-11-01", "currency": "USD", "total": "5.00"}
            assert client.post("/receipts/manual", json=manual, headers=headers).status_code == 201
            container.assistant.save_question(login["user"]["id"], None, "How much did I spend?")
            people.append((login["user"]["id"], headers))
        (alice, alice_headers), (bob, bob_headers) = people
        assert list((tmp_path / str(alice)).iterdir()) and list((tmp_path / str(bob)).iterdir())

        container.auth.delete_account(alice)

        assert client.get("/auth/me", headers=alice_headers).status_code == 401  # the old token no longer works
        assert list((tmp_path / str(alice)).iterdir()) == []
        with user_scoped_connection(engine, alice) as conn:
            for table in ("receipts", "receipt_items", "conversations", "notifications"):
                assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0, table
        with user_scoped_connection(engine, bob) as conn:  # Bob keeps everything
            assert conn.execute(text("SELECT count(*) FROM receipts")).scalar() == 2
            assert conn.execute(text("SELECT count(*) FROM conversations")).scalar() == 1
        assert len(list((tmp_path / str(bob)).iterdir())) == 1
        assert client.get("/auth/me", headers=bob_headers).status_code == 200
        with pytest.raises(InvalidToken):
            container.auth.delete_account(alice)
    finally:
        with engine.begin() as conn:
            for address in emails:
                conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": address})
