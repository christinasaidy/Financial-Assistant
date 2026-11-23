from datetime import date
from typing import Protocol

from app.application.assistant.dtos import QueryResult, TurnRequest, WorkflowAnswer
from app.domain.assistant.conversation import (
    DEFAULT_MODE,
    AnswerDetails,
    AssistantMode,
    Conversation,
    Message,
    MessageRole,
    Rating,
    Turn,
)
from app.domain.assistant.prompt import UserNames


class SqlGuard(Protocol):
    def check(self, sql: str) -> str:
        """Return the SQL that may run (rebuilt from what was checked), or raise UnsafeQuery."""


class QueryRules(Protocol):
    """The answering rules for SQL that the guard already found safe."""

    def prepare(self, sql: str, names: UserNames, today: date) -> str:
        """Raise QueryRejected if the SQL breaks an answering rule (a loose or unknown name, the clock read
        directly); otherwise return it with CURRENT_DATE replaced by `today`."""

    def check_dates(self, sql: str, asked: str, today: date) -> None:
        """Raise QueryRejected if the SQL's dates were not asked for: only yesterday when `asked` (the earlier
        questions and the question) never names it, or last year's month when this year's has come and no year
        was mentioned."""

    def sizes_query(self, sql: str) -> str | None:
        """For a price comparison of one item between named shops: a query of the (vendor, size kind) pairs the
        item has there under the SQL's other conditions. None for any other SQL."""

    def size_hint(self, sql: str, result: QueryResult, sizes: QueryResult) -> str | None:
        """When the comparison's result misses a named shop and the item has a size kind at every one of them that
        the SQL left out: how to compare by it. Otherwise None."""

    def describe(self, sql: str) -> str | None:
        """What a query that ran looked at, for the line under its answer ("Looked at: laban at Spinneys, 1–31
        October 2026"), read from its conditions. None when any of them cannot be read, rather than a guess."""

    def sources_query(self, sql: str) -> str | None:
        """A query for the receipt_ids the result is based on, or None when it cannot be worked out reliably
        (a UNION, a WITH, or a subquery in FROM)."""


class ReadOnlyQueryRunner(Protocol):
    def run(self, user_id: int, sql: str) -> QueryResult:
        """Run already-checked SQL as the read-only assistant role, seeing only this user's rows.
        Raises QueryFailed if the database cannot run it."""


class AssistantModel(Protocol):
    """The language model. It writes the SQL (the fine-tuned adapter, once there is one) and the answers (the same
    base model without the adapter). Both raise ModelFailed if no usable response comes back, and
    ModelUnavailable if no model is configured."""

    sql_model: str  # the model names, saved with every attempt
    answer_model: str

    def write_sql(self, prompt: str) -> str: ...

    def write_answer(self, prompt: str) -> str: ...


class StandardAssistant(Protocol):
    """The Standard mode's workflow: a hosted model with its own prompt and the app's read-only tools. It answers one
    question and returns the answer to save; the service saves it and ends the turn. It handles its own model and
    tool failures by returning an error answer; anything it raises fails the turn."""

    model: str  # the configured model, shown by GET /assistant/modes

    def answer(self, request: TurnRequest) -> WorkflowAnswer: ...


class ConversationRepository(Protocol):
    def create(self, title: str, mode: AssistantMode = DEFAULT_MODE) -> int: ...

    def exists(self, conversation_id: int) -> bool: ...

    def mode_of(self, conversation_id: int) -> AssistantMode | None:
        """None if there is no such conversation for this user."""

    def hold(self, conversation_id: int) -> bool:
        """Keep the conversation from being deleted until this transaction ends. False if it no longer exists."""

    def list_all(self) -> list[Conversation]:
        """Newest activity first, without messages."""

    def get(self, conversation_id: int) -> Conversation | None:
        """Without messages."""

    def delete(self, conversation_id: int) -> bool:
        """Its messages and ratings go with it. Returns False if there is no such conversation."""


class MessageRepository(Protocol):
    def add(
        self, conversation_id: int, role: MessageRole, content: str, details: AnswerDetails | None = None
    ) -> Message: ...

    def list_for(self, conversation_id: int) -> list[Message]:
        """Oldest first, each with its current rating."""

    def get(self, message_id: int) -> Message | None:
        """With its current rating. None if there is no such message for this user."""

    def role_of(self, message_id: int) -> MessageRole | None:
        """None if there is no such message for this user."""


class FeedbackRepository(Protocol):
    def set(self, message_id: int, rating: Rating) -> None:
        """Create or replace the rating of an assistant answer."""

    def clear(self, message_id: int) -> bool: ...


class TurnRepository(Protocol):
    """Answering one question. The database enforces that a conversation has at most one running turn, that a key
    is used once per user, and that only a running turn can complete or fail."""

    def start(
        self, conversation_id: int, question_message_id: int, mode: AssistantMode, idempotency_key: str | None
    ) -> int | None:
        """A new running turn's id, or None when the conversation already has a running turn or the key was used
        (by a request that may have committed only just now)."""

    def give_up_abandoned(self, conversation_id: int, older_than_seconds: float) -> int:
        """Mark the conversation's running turn failed ("abandoned") if it started longer ago than that: its
        worker stopped or hung. Returns how many were given up (0 or 1)."""

    def find_by_key(self, idempotency_key: str) -> Turn | None: ...

    def get(self, turn_id: int) -> Turn | None: ...

    def complete(self, turn_id: int, answer_message_id: int, execution: dict | None = None) -> bool:
        """False (and nothing changes) if the turn is no longer running or no longer exists."""

    def fail(self, turn_id: int, problem: str) -> bool:
        """False (and nothing changes) if the turn is no longer running or no longer exists."""
