from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt

from app.application.auth.ports import AccessToken
from app.domain.users.errors import InvalidToken

MIN_SECRET_LENGTH = 32


class JwtTokenService:
    ALGORITHM = "HS256"

    def __init__(
        self,
        secret: str,
        expire_minutes: int = 60,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if len(secret) < MIN_SECRET_LENGTH:
            raise ValueError(f"JWT secret must be at least {MIN_SECRET_LENGTH} characters")
        self._secret = secret
        self._lifetime = timedelta(minutes=expire_minutes)
        self._clock = clock

    def issue(self, user_id: int) -> AccessToken:
        now = self._clock()
        claims = {"sub": str(user_id), "iat": now, "exp": now + self._lifetime}
        token = jwt.encode(claims, self._secret, algorithm=self.ALGORITHM)
        return AccessToken(token=token, expires_in=int(self._lifetime.total_seconds()))

    def verify(self, token: str) -> int:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[self.ALGORITHM],  # never trust the algorithm named in the token
                options={"require": ["exp", "iat", "sub"]},
            )
            return int(claims["sub"])
        except (jwt.PyJWTError, ValueError) as exc:
            raise InvalidToken("Invalid or expired token") from exc
