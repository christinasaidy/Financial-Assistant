import pytest

from app.application.auth.dtos import LoginRequest, RegisterRequest
from app.application.auth.get_current_user import GetCurrentUser
from app.application.auth.login import Login
from app.application.auth.register_user import RegisterUser
from app.domain.users.errors import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidEmail,
    InvalidToken,
    WeakPassword,
)
from app.infrastructure.security.token_service import JwtTokenService
from tests.fakes import FakeHasher, InMemoryUserRepository

SECRET = "x" * 40


@pytest.fixture
def users():
    return InMemoryUserRepository()


@pytest.fixture
def tokens():
    return JwtTokenService(SECRET)


@pytest.fixture
def register(users):
    return RegisterUser(users, FakeHasher())


@pytest.fixture
def login(users, tokens):
    return Login(users, FakeHasher(), tokens)


def test_register_returns_the_normalized_user(register):
    user = register.execute(RegisterRequest("  Christina@Example.com ", "correct-horse"))
    assert user.email == "christina@example.com"


def test_password_is_stored_hashed_not_plain(register, users):
    register.execute(RegisterRequest("a@b.com", "correct-horse"))
    stored = users.get_credentials_by_email("a@b.com")
    assert stored.password_hash != "correct-horse"


def test_duplicate_email_is_rejected_case_insensitively(register):
    register.execute(RegisterRequest("a@b.com", "correct-horse"))
    with pytest.raises(EmailAlreadyRegistered):
        register.execute(RegisterRequest("A@B.com", "another-password"))


def test_register_rejects_bad_email_and_weak_password(register):
    with pytest.raises(InvalidEmail):
        register.execute(RegisterRequest("nope", "correct-horse"))
    with pytest.raises(WeakPassword):
        register.execute(RegisterRequest("a@b.com", "short"))


def test_login_returns_a_token_for_the_right_user(register, login, tokens):
    user = register.execute(RegisterRequest("a@b.com", "correct-horse"))
    result = login.execute(LoginRequest("A@B.com", "correct-horse"))
    assert result.user == user
    assert tokens.verify(result.access_token) == user.id


def test_wrong_password_unknown_email_and_bad_email_look_the_same(register, login):
    register.execute(RegisterRequest("a@b.com", "correct-horse"))
    for email, password in [("a@b.com", "wrong-password"), ("nobody@b.com", "correct-horse"), ("not-an-email", "x")]:
        with pytest.raises(InvalidCredentials):
            login.execute(LoginRequest(email, password))


def test_current_user_lookup(register, users):
    user = register.execute(RegisterRequest("a@b.com", "correct-horse"))
    assert GetCurrentUser(users).execute(user.id) == user


def test_token_for_a_deleted_account_is_rejected(register, users):
    user = register.execute(RegisterRequest("a@b.com", "correct-horse"))
    users.delete(user.id)
    with pytest.raises(InvalidToken):
        GetCurrentUser(users).execute(user.id)
