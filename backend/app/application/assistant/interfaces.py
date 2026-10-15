from typing import Protocol

from app.application.assistant.dtos import QueryResult
from app.domain.assistant.conversation import AnswerDetails, Conversation, Message, MessageRole, Rating


class SqlGuard(Protocol):
    def check(self, sql: str) -> str:
        """Return the SQL that may run (rebuilt from what was checked), or raise UnsafeQuery."""


class ReadOnlyQueryRunner(Protocol):
    def run(self, user_id: int, sql: str) -> QueryResult:
        """Run already-checked SQL as the read-only assistant role, seeing only this user's rows.
        Raises QueryFailed if the database cannot run it."""


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

