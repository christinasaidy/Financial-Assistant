from app.application.auth.dtos import RegisterRequest, UserResponse
from app.application.auth.ports import PasswordHasher, UserRepository
from app.domain.users.user import normalize_email, validate_password


class RegisterUser:
    def __init__(self, users: UserRepository, hasher: PasswordHasher) -> None:
        self._users = users
        self._hasher = hasher

    def execute(self, request: RegisterRequest) -> UserResponse:
        email = normalize_email(request.email)
        validate_password(request.password)
        user = self._users.add(email, self._hasher.hash(request.password))
        return UserResponse(id=user.id, email=user.email)
