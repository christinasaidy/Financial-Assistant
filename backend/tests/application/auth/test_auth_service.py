import pytest

from app.application.auth.auth_service import AuthService
from app.application.auth.dtos import LoginRequest, RegisterRequest
from app.domain.users.errors import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidEmail,
    InvalidFirstName,
    InvalidGender,
    InvalidToken,
    WeakPassword,
)
from app.domain.users.user import Gender
from app.infrastructure.security.token_service import JwtTokenService
from tests.fakes import FakeHasher, InMemoryFileStorage, InMemoryUserRepository

SECRET = "x" * 40


@pytest.fixture
def users():
    return InMemoryUserRepository()


@pytest.fixture
def files():
    return InMemoryFileStorage()


@pytest.fixture
def auth(users, files):
    return AuthService(users, FakeHasher(), JwtTokenService(SECRET), files)


def test_register_returns_the_normalized_user(auth):
    user = auth.register(RegisterRequest("  Christina@Example.com ", "correct-horse", "  Christina ", "female"))
    assert user.email == "christina@example.com"
    assert user.first_name == "Christina"
    assert user.gender is Gender.FEMALE


def test_register_stores_the_first_name_and_gender(auth, users):
    user = auth.register(RegisterRequest("a@b.com", "correct-horse", "Rami", "prefer_not_to_say"))
    stored = users.get_by_id(user.id)
    assert (stored.first_name, stored.gender) == ("Rami", Gender.PREFER_NOT_TO_SAY)


@pytest.mark.parametrize("first_name", ["", "   ", "x" * 51])
def test_register_rejects_a_blank_or_too_long_first_name_and_creates_nothing(auth, users, first_name):
    with pytest.raises(InvalidFirstName):
        auth.register(RegisterRequest("a@b.com", "correct-horse", first_name, "female"))
    assert users.get_credentials_by_email("a@b.com") is None


def test_register_rejects_an_unknown_gender_and_creates_nothing(auth, users):
    with pytest.raises(InvalidGender):
        auth.register(RegisterRequest("a@b.com", "correct-horse", "Christina", "other"))
    assert users.get_credentials_by_email("a@b.com") is None


def test_password_is_stored_hashed_not_plain(auth, users):
    auth.register(RegisterRequest("a@b.com", "correct-horse", "Christina", "female"))
    stored = users.get_credentials_by_email("a@b.com")
    assert stored.password_hash != "correct-horse"


def test_duplicate_email_is_rejected_case_insensitively(auth):
    auth.register(RegisterRequest("a@b.com", "correct-horse", "Christina", "female"))
    with pytest.raises(EmailAlreadyRegistered):
        auth.register(RegisterRequest("A@B.com", "another-password", "Christina", "female"))


def test_register_rejects_bad_email_and_weak_password(auth):
    with pytest.raises(InvalidEmail):
        auth.register(RegisterRequest("nope", "correct-horse", "Christina", "female"))
    with pytest.raises(WeakPassword):
        auth.register(RegisterRequest("a@b.com", "short", "Christina", "female"))


def test_login_returns_a_token_for_the_right_user(auth):
    user = auth.register(RegisterRequest("a@b.com", "correct-horse", "Christina", "female"))
    result = auth.login(LoginRequest("A@B.com", "correct-horse"))
    assert result.user == user  # with the first name and gender
    assert auth.authenticate(result.access_token) == user.id


def test_wrong_password_unknown_email_and_bad_email_look_the_same(auth):
    auth.register(RegisterRequest("a@b.com", "correct-horse", "Christina", "female"))
    for email, password in [("a@b.com", "wrong-password"), ("nobody@b.com", "correct-horse"), ("not-an-email", "x")]:
        with pytest.raises(InvalidCredentials):
            auth.login(LoginRequest(email, password))


def test_authenticate_rejects_a_token_it_did_not_issue(auth):
    with pytest.raises(InvalidToken):
        auth.authenticate("garbage")
    with pytest.raises(InvalidToken):
        auth.authenticate(JwtTokenService("o" * 40).issue(1).token)


def test_current_user_lookup(auth):
    user = auth.register(RegisterRequest("a@b.com", "correct-horse", "Christina", "female"))
    assert auth.get_current_user(user.id) == user
    assert (user.first_name, user.gender) == ("Christina", Gender.FEMALE)


def test_token_for_a_deleted_account_is_rejected(auth, users):
    user = auth.register(RegisterRequest("a@b.com", "correct-horse", "Christina", "female"))
    users.delete(user.id)
    with pytest.raises(InvalidToken):
        auth.get_current_user(user.id)


def test_authenticate_rejects_a_valid_token_once_the_account_is_gone(auth, users):
    user = auth.register(RegisterRequest("a@b.com", "correct-horse", "Christina", "female"))
    token = auth.login(LoginRequest("a@b.com", "correct-horse")).access_token
    assert auth.authenticate(token) == user.id
    users.delete(user.id)
    with pytest.raises(InvalidToken):
        auth.authenticate(token)


# --- Deleting an account (no endpoint yet; approved by the user on 2026-11-05) ---


def test_deleting_an_account_removes_the_user_and_only_their_files(auth, users, files):
    alice = auth.register(RegisterRequest("alice@b.com", "correct-horse", "Alice", "female")).id
    bob = auth.register(RegisterRequest("bob@b.com", "correct-horse", "Bob", "male")).id
    files.save(alice, b"img", ".jpg")
    files.save(alice, b"img", ".pdf")
    files.save(bob, b"img", ".jpg")

    auth.delete_account(alice)

    assert users.get_by_id(alice) is None
    assert files.files[alice] == [] and len(files.files[bob]) == 1
    with pytest.raises(InvalidToken):
        auth.get_current_user(alice)


def test_deleting_an_account_that_is_gone_is_refused_and_touches_no_file(auth, files):
    files.save(12345, b"img", ".jpg")  # rows are deleted first: if that fails, no file may be lost
    with pytest.raises(InvalidToken, match="no longer exists"):
        auth.delete_account(12345)
    assert len(files.files[12345]) == 1


def test_a_file_that_cannot_be_removed_is_left_for_the_clean_up(auth, users, files, caplog):
    alice = auth.register(RegisterRequest("alice@b.com", "correct-horse", "Alice", "female")).id
    stuck = files.save(alice, b"img", ".jpg")
    files.save(alice, b"img", ".pdf")
    files.cannot_delete.add(stuck)

    auth.delete_account(alice)

    assert users.get_by_id(alice) is None  # the account is deleted anyway
    assert files.files[alice] == [stuck]
    assert "left for the orphan clean-up" in caplog.text
