from datetime import date
from typing import Protocol

from app.application.assistant.dtos import QueryResult
from app.domain.assistant.conversation import AnswerDetails, Conversation, Message, MessageRole, Rating
from app.domain.assistant.prompt import UserNames


class SqlGuard(Protocol):
    def check(self, sql: str) -> str:
        """Return the SQL that may run (rebuilt from what was checked), or raise UnsafeQuery."""


class QueryRules(Protocol):
    """The answering rules for SQL that the guard already found safe."""

    def prepare(self, sql: str, names: UserNames, today: date) -> str:
        """Raise QueryRejected if the SQL breaks an answering rule (a loose or unknown name, the clock read
        directly); otherwise return it with CURRENT_DATE replaced by `today`."""

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


class ConversationRepository(Protocol):
    def create(self, title: str) -> int: ...

    def exists(self, conversation_id: int) -> bool: ...

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

    def role_of(self, message_id: int) -> MessageRole | None:
        """None if there is no such message for this user."""


class FeedbackRepository(Protocol):
    def set(self, message_id: int, rating: Rating) -> None:
        """Create or replace the rating of an assistant answer."""

    def clear(self, message_id: int) -> bool: ...
