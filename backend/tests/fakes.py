"""In-memory stand-ins for the interfaces, so services and the API can be tested without a database."""

from app.application.auth.interfaces import StoredCredentials
from app.domain.receipts.errors import ExtractionFailed
from app.domain.receipts.extraction import ExtractedReceipt
from app.domain.users.errors import EmailAlreadyRegistered
from app.domain.users.user import User


class FakeReceiptExtractor:
    """Returns a fixed extraction, or fails, and records how often it was called."""

    def __init__(self, result: ExtractedReceipt | None = None) -> None:
        self.result = result  # None means "the model could not read it"
        self.calls = 0
        self.category_names: list[str] = []
        self.known_names: list[str] = []

    def extract(self, content: bytes, content_type: str, category_names, known_names=()) -> ExtractedReceipt:
        self.calls += 1
        self.category_names = list(category_names)
        self.known_names = list(known_names)
        if self.result is None:
            raise ExtractionFailed
        return self.result


class FakeHasher:
    """Fast and obviously not secure: only for tests."""

    def hash(self, password: str) -> str:
        return f"hashed::{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed::{password}"


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._rows: dict[int, tuple[str, str]] = {}  # id -> (email, password_hash)
        self._next_id = 1

    def add(self, email: str, password_hash: str) -> User:
        if any(existing == email for existing, _ in self._rows.values()):
            raise EmailAlreadyRegistered("Email is already registered")
        user_id = self._next_id
        self._next_id += 1
        self._rows[user_id] = (email, password_hash)
        return User(id=user_id, email=email)

    def get_credentials_by_email(self, email: str) -> StoredCredentials | None:
        for user_id, (stored_email, password_hash) in self._rows.items():
            if stored_email == email:
                return StoredCredentials(User(user_id, stored_email), password_hash)
        return None

    def get_by_id(self, user_id: int) -> User | None:
        if user_id not in self._rows:
            return None
        return User(user_id, self._rows[user_id][0])

    def delete(self, user_id: int) -> None:
        self._rows.pop(user_id, None)
