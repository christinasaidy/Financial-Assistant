"""In-memory stand-ins for the interfaces, so services and the API can be tested without a database."""

import threading
from datetime import UTC, datetime

from app.application.assistant.dtos import (
    ChatRequest,
    ChatResponse,
    ModelUsage,
    TextPart,
    ToolCall,
    TurnRequest,
    WorkflowAnswer,
)
from app.application.auth.interfaces import StoredCredentials
from app.application.receipts.interfaces import StoredFile
from app.domain.assistant.conversation import AnswerDetails, AnswerKind, Attempt, Step
from app.domain.receipts.errors import ExtractionFailed
from app.domain.receipts.extraction import ExtractedReceipt
from app.domain.users.errors import EmailAlreadyRegistered
from app.domain.users.user import Gender, User


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
        self._rows: dict[int, tuple[User, str]] = {}  # id -> (user, password_hash)
        self._next_id = 1

    def add(self, email: str, password_hash: str, first_name: str, gender: Gender) -> User:
        if any(user.email == email for user, _ in self._rows.values()):
            raise EmailAlreadyRegistered("Email is already registered")
        user = User(id=self._next_id, email=email, first_name=first_name, gender=gender)
        self._next_id += 1
        self._rows[user.id] = (user, password_hash)
        return user

    def get_credentials_by_email(self, email: str) -> StoredCredentials | None:
        for user, password_hash in self._rows.values():
            if user.email == email:
                return StoredCredentials(user, password_hash)
        return None

    def get_by_id(self, user_id: int) -> User | None:
        if user_id not in self._rows:
            return None
        return self._rows[user_id][0]

    def delete(self, user_id: int) -> bool:
        return self._rows.pop(user_id, None) is not None


class FakeStandardAssistant:
    """Stands in for the Standard workflow: answers every question with `reply` and records each request. If
    `hold` is set, it waits until `release` is set before answering (to keep a turn running); a `fail` exception is
    raised instead of answering."""

    model = "fake-standard-model"

    def __init__(self, reply: str = "Standard answer") -> None:
        self.reply = reply
        self.requests: list[TurnRequest] = []
        self.fail: Exception | None = None
        self.hold = False
        self.started = threading.Event()  # set once a request has arrived
        self.release = threading.Event()

    def answer(self, request: TurnRequest) -> WorkflowAnswer:
        self.requests.append(request)
        self.started.set()
        if self.hold:
            assert self.release.wait(10), "the test never released the held answer"
        if self.fail is not None:
            raise self.fail
        attempt = Attempt(Step.ANSWER, self.model, self.reply)
        return WorkflowAnswer(self.reply, AnswerDetails(AnswerKind.REPLY, attempts=(attempt,)), {"fake": True})


class ScriptedChatModel:
    """Stands in for the Standard mode's hosted model: returns the scripted responses in order (a ModelFailed in the
    script is raised instead) and records every request it was sent."""

    model = "fake-sonnet"

    def __init__(self, *script) -> None:
        self.script = list(script)
        self.requests: list[ChatRequest] = []

    def respond(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        if not self.script:
            raise AssertionError("the model was called more often than the test expected")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def says(text: str, usage: ModelUsage | None = ModelUsage(10, 5, 0, 0)) -> ChatResponse:
    """A finished model reply."""
    return ChatResponse((TextPart(text),), "end_turn", "fake-sonnet", usage, "req_text", ("provider", text))


def calls(*tool_calls: tuple[str, str, dict], usage: ModelUsage | None = ModelUsage(10, 5, 0, 0)) -> ChatResponse:
    """A model reply asking for tools: (id, name, input) each."""
    parts = tuple(ToolCall(call_id, name, args) for call_id, name, args in tool_calls)
    return ChatResponse(parts, "tool_use", "fake-sonnet", usage, "req_tools", ("provider", tool_calls))
