from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.container import AuthServices, Container
from app.application.auth.get_current_user import GetCurrentUser
from app.application.auth.login import Login
from app.application.auth.register_user import RegisterUser
from app.infrastructure.security.token_service import JwtTokenService
from tests.fakes import FakeHasher, InMemoryUserRepository

SECRET = "t" * 40


@pytest.fixture
def client():
    users, hasher, tokens = InMemoryUserRepository(), FakeHasher(), JwtTokenService(SECRET)
    auth = AuthServices(
        register_user=RegisterUser(users, hasher),
        login=Login(users, hasher, tokens),
        get_current_user=GetCurrentUser(users),
        tokens=tokens,
    )
    # Only the auth routes are exercised here, so the other feature groups are stand-ins.
    return TestClient(create_app(Container(auth=auth, receipts=Mock(), categories=Mock())))


def register(client, email="a@b.com", password="correct-horse"):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client, email="a@b.com", password="correct-horse"):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_register_then_login_then_me(client):
    assert register(client).status_code == 201
    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert "password" not in str(body)

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "a@b.com"


def test_register_never_returns_the_password_or_hash(client):
    body = register(client).json()
    assert set(body) == {"id", "email"}


def test_duplicate_registration_is_a_conflict(client):
    register(client)
    assert register(client, email="A@B.COM").status_code == 409


def test_bad_registration_input_is_unprocessable(client):
    assert register(client, email="nope").status_code == 422
    assert register(client, password="short").status_code == 422


def test_failed_logins_all_give_the_same_401(client):
    register(client)
    wrong_password = login(client, password="wrong-password")
    unknown_email = login(client, email="nobody@b.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_me_requires_a_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401
