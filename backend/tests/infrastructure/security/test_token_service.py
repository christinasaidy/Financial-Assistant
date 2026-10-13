from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.domain.users.errors import InvalidToken
from app.infrastructure.security.token_service import JwtTokenService

SECRET = "s" * 40


def test_token_round_trip():
    service = JwtTokenService(SECRET, expire_minutes=30)
    token = service.issue(42)
    assert token.expires_in == 30 * 60
    assert service.verify(token.token) == 42


def test_expired_token_is_rejected():
    past = lambda: datetime.now(UTC) - timedelta(hours=2)  # noqa: E731
    token = JwtTokenService(SECRET, expire_minutes=60, clock=past).issue(1)
    with pytest.raises(InvalidToken):
        JwtTokenService(SECRET).verify(token.token)


def test_token_signed_with_another_key_is_rejected():
    token = JwtTokenService("o" * 40).issue(1)
    with pytest.raises(InvalidToken):
        JwtTokenService(SECRET).verify(token.token)


def test_tampered_token_is_rejected():
    token = JwtTokenService(SECRET).issue(1).token
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(InvalidToken):
        JwtTokenService(SECRET).verify(tampered)


def test_unsigned_alg_none_token_is_rejected():
    now = datetime.now(UTC)
    forged = jwt.encode({"sub": "1", "iat": now, "exp": now + timedelta(hours=1)}, key=None, algorithm="none")
    with pytest.raises(InvalidToken):
        JwtTokenService(SECRET).verify(forged)


def test_token_missing_required_claims_is_rejected():
    no_exp = jwt.encode({"sub": "1", "iat": datetime.now(UTC)}, SECRET, algorithm="HS256")
    non_numeric_sub = jwt.encode(
        {"sub": "abc", "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(hours=1)},
        SECRET,
        algorithm="HS256",
    )
    for token in (no_exp, non_numeric_sub, "garbage"):
        with pytest.raises(InvalidToken):
            JwtTokenService(SECRET).verify(token)


def test_short_secret_is_refused():
    with pytest.raises(ValueError):
        JwtTokenService("too-short")
