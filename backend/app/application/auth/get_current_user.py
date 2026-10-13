from app.application.auth.dtos import UserResponse
from app.application.auth.ports import UserRepository
from app.domain.users.errors import InvalidToken


class GetCurrentUser:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(self, user_id: int) -> UserResponse:
        user = self._users.get_by_id(user_id)
        if user is None:
            # A valid token for an account that no longer exists.
            raise InvalidToken("Account no longer exists")
        return UserResponse(id=user.id, email=user.email)
