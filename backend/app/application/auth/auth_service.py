import logging

from app.application.auth.dtos import LoginRequest, LoginResponse, RegisterRequest, UserResponse
from app.application.auth.interfaces import PasswordHasher, TokenService, UserRepository
from app.application.receipts.interfaces import FileStorage
from app.domain.users.errors import InvalidCredentials, InvalidEmail, InvalidToken
from app.domain.users.user import normalize_email, validate_password

logger = logging.getLogger(__name__)


class AuthService:
    """Everything to do with accounts and signing in."""

    def __init__(self, users: UserRepository, hasher: PasswordHasher, tokens: TokenService, files: FileStorage) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        self._files = files  # the receipt images, so a deleted account leaves none behind
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

    def delete_account(self, user_id: int) -> None:
        """Delete the account, everything it owns and its receipt files. No endpoint calls this yet (to come with the
        app's settings screen, with the password asked again); the research evaluation uses it for its throwaway user.

        Rows first, files second, as for a single receipt: a failed delete never loses an image, and a file that
        cannot be removed now is logged and left for the orphan clean-up (no receipt points at it any more)."""
        if not self._users.delete(user_id):
            raise InvalidToken("Account no longer exists")
        for stored in self._files.list_files(user_id):
            try:
                self._files.delete(stored.path)
            except Exception:
                logger.exception("Could not remove %s of a deleted account; it is left for the orphan clean-up",
                                 stored.path)  # fmt: skip

    def get_current_user(self, user_id: int) -> UserResponse:
        user = self._users.get_by_id(user_id)
        if user is None:
            # A valid token for an account that no longer exists.
            raise InvalidToken("Account no longer exists")
        return UserResponse(id=user.id, email=user.email)
