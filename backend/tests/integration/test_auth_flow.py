"""Auth against the real database: the SQL repository and the full API wiring from app.main."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.domain.users.errors import EmailAlreadyRegistered
from app.infrastructure.config import Settings
from app.infrastructure.database.connection import user_scoped_connection
from app.infrastructure.database.user_repository import SqlUserRepository
from app.main import build_app


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
