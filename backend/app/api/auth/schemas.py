from pydantic import BaseModel

from app.application.auth.dtos import UserResponse


class RegisterBody(BaseModel):
    email: str
    password: str
    first_name: str
    gender: str  # female, male or prefer_not_to_say


class LoginBody(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    first_name: str | None  # None only for accounts made before names were asked
    gender: str | None

    @classmethod
    def from_user(cls, user: UserResponse) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            gender=user.gender.value if user.gender else None,
        )


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
