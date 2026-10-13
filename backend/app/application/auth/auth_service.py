from app.application.auth.dtos import LoginRequest, LoginResponse, RegisterRequest, UserResponse
from app.application.auth.interfaces import PasswordHasher, TokenService, UserRepository
from app.domain.users.errors import InvalidCredentials, InvalidEmail, InvalidToken
from app.domain.users.user import normalize_email, validate_password


class AuthService:
    """Everything to do with accounts and signing in."""

    def __init__(self, users: UserRepository, hasher: PasswordHasher, tokens: TokenService) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        # Checked when the email is unknown, so unknown and known emails take similar time.
        self._decoy_hash = hasher.hash("decoy-password-never-matches")

    def register(self, request: RegisterRequest) -> UserResponse:
        email = normalize_email(request.email)
        validate_password(request.password)
        user = self._users.add(email, self._hasher.hash(request.password))
        return UserResponse(id=user.id, email=user.email)

    def login(self, request: LoginRequest) -> LoginResponse:
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

    def authenticate(self, token: str) -> int:
        """The user id a bearer token belongs to. Raises InvalidToken if it cannot be trusted."""
        user_id = self._tokens.verify(token)
        # A token outlives its account by up to an hour, so check the account is still there.
        if self._users.get_by_id(user_id) is None:
            raise InvalidToken("Account no longer exists")
        return user_id

    def get_current_user(self, user_id: int) -> UserResponse:
        user = self._users.get_by_id(user_id)
        if user is None:
            # A valid token for an account that no longer exists.
            raise InvalidToken("Account no longer exists")
        return UserResponse(id=user.id, email=user.email)
