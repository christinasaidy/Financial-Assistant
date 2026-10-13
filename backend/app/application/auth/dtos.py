"""Plain request and response objects that cross the application boundary."""

from dataclasses import dataclass


@dataclass(frozen=True)
class UserResponse:
    id: int
    email: str


@dataclass(frozen=True)
class RegisterRequest:
    email: str
    password: str


@dataclass(frozen=True)
class LoginRequest:
    email: str
    password: str


@dataclass(frozen=True)
class LoginResponse:
    access_token: str
    expires_in: int
    user: UserResponse
