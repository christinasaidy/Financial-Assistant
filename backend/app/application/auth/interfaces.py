"""Interfaces the application layer needs. Infrastructure implements them."""

from dataclasses import dataclass
from typing import Protocol

from app.domain.users.user import User


@dataclass(frozen=True)
class StoredCredentials:
    user: User
    password_hash: str


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_in: int  # seconds


class UserRepository(Protocol):
    def add(self, email: str, password_hash: str) -> User:
        """Create a user. Raises EmailAlreadyRegistered if the email is taken."""

    def get_credentials_by_email(self, email: str) -> StoredCredentials | None: ...

    def get_by_id(self, user_id: int) -> User | None: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class TokenService(Protocol):
    def issue(self, user_id: int) -> AccessToken: ...

    def verify(self, token: str) -> int:
        """Return the user id the token was issued for. Raises InvalidToken otherwise."""
