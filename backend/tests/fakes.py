"""In-memory stand-ins for the interfaces, so services and the API can be tested without a database."""

from datetime import UTC, datetime

from app.application.auth.interfaces import StoredCredentials
from app.application.receipts.interfaces import StoredFile
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


class FakeAssistantModel:
    """Gives the replies it was set up with, in order, and records every prompt. A reply that is an exception is
    raised instead. A call it has no reply for fails the test, so a test also proves how many calls were made."""

    sql_model = "fake-sql-model"
    answer_model = "fake-answer-model"

    def __init__(self, sql=(), answers=()) -> None:
        self.sql_replies = list(sql)
        self.answer_replies = list(answers)
        self.sql_prompts: list[str] = []
        self.answer_prompts: list[str] = []

    def write_sql(self, prompt: str) -> str:
        self.sql_prompts.append(prompt)
        return self._next(self.sql_replies, "SQL")

    def write_answer(self, prompt: str) -> str:
        self.answer_prompts.append(prompt)
        return self._next(self.answer_replies, "answer")

    @staticmethod
    def _next(replies: list, step: str) -> str:
        if not replies:
            raise AssertionError(f"The model was asked for an unexpected {step} reply")
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class InMemoryFileStorage:
    """Files by user, in memory. Paths in `cannot_delete` raise like a locked file would."""

    def __init__(self) -> None:
        self.files: dict[int, list[str]] = {}
        self.cannot_delete: set[str] = set()

    def save(self, user_id: int, content: bytes, extension: str) -> str:
        path = f"{user_id}/{len(self.files.get(user_id, []))}{extension}"
        self.files.setdefault(user_id, []).append(path)
        return path

    def read(self, path: str) -> bytes:
        return b""

    def delete(self, path: str) -> None:
        if path in self.cannot_delete:
            raise PermissionError(path)
        for paths in self.files.values():
            if path in paths:
                paths.remove(path)

    def user_ids(self) -> list[int]:
        return [user_id for user_id, paths in self.files.items() if paths]

    def list_files(self, user_id: int) -> list[StoredFile]:
        return [StoredFile(path, datetime.now(UTC)) for path in self.files.get(user_id, [])]


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

    def delete(self, user_id: int) -> bool:
        return self._rows.pop(user_id, None) is not None
