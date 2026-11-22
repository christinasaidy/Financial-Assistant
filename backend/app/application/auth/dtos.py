"""Plain request and response objects that cross the application boundary."""

from dataclasses import dataclass

from app.domain.users.user import Gender


@dataclass(frozen=True)
class UserResponse:
    id: int
    email: str
    first_name: str | None  # None only for accounts made before names were asked
    gender: Gender | None


@dataclass(frozen=True)
class RegisterRequest:
    email: str
    password: str
    first_name: str
    gender: str  # female, male or prefer_not_to_say


@dataclass(frozen=True)
class LoginRequest:
    email: str
    password: str


@dataclass(frozen=True)
class LoginResponse:
    access_token: str
    expires_in: int
    user: UserResponse
