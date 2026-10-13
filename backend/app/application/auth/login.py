from app.application.auth.dtos import LoginRequest, LoginResponse, UserResponse
from app.application.auth.ports import PasswordHasher, TokenService, UserRepository
from app.domain.users.errors import InvalidCredentials, InvalidEmail
from app.domain.users.user import normalize_email


class Login:
    def __init__(self, users: UserRepository, hasher: PasswordHasher, tokens: TokenService) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        # Checked when the email is unknown, so unknown and known emails take similar time.
        self._decoy_hash = hasher.hash("decoy-password-never-matches")

    def execute(self, request: LoginRequest) -> LoginResponse:
        try:
            email = normalize_email(request.email)
        except InvalidEmail:
            raise InvalidCredentials from None

        stored = self._users.get_credentials_by_email(email)
        password_hash = stored.password_hash if stored else self._decoy_hash
        password_ok = self._hasher.verify(request.password, password_hash)
        if stored is None or not password_ok:
            raise InvalidCredentials

        token = self._tokens.issue(stored.user.id)
        return LoginResponse(
            access_token=token.token,
            expires_in=token.expires_in,
            user=UserResponse(id=stored.user.id, email=stored.user.email),
        )
