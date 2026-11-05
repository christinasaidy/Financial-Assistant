from dataclasses import dataclass
from datetime import datetime

from app.domain.assistant.answer import ModelReply
from app.domain.assistant.conversation import AnswerDetails, Attempt, Conversation, MessageRole, Rating


@dataclass(frozen=True)
class QueryResult:
    sql: str  # exactly what ran
    columns: list[str]
    rows: list[tuple]
    truncated: bool  # more rows existed than the limit allows


@dataclass(frozen=True)
class SavedQuestion:
    conversation_id: int
    message_id: int


@dataclass(frozen=True)
class SourceReceipt:
    receipt_id: int
    available: bool  # False once the receipt has been deleted


@dataclass(frozen=True)
class MessageView:
    id: int
    role: MessageRole
    content: str
    created_at: datetime
    details: AnswerDetails | None
    source_receipts: list[SourceReceipt]
    rating: Rating | None


@dataclass(frozen=True)
class ConversationView:
    conversation: Conversation
    messages: list[MessageView]


@dataclass(frozen=True)
class AskResult:
    conversation_id: int  # the new conversation's id when the question started one
    answer: MessageView


@dataclass(frozen=True)
class QuestionOutcome:
    """What the SQL step came to (`AssistantService.run_question`). At most one of `result` and `reply` is set;
    neither means both attempts failed or the model could not be reached."""

    result: QueryResult | None  # the query's result, when the model wrote usable SQL
    reply: ModelReply | None  # or its clarifying question, refusal or short reply
    attempts: tuple[Attempt, ...]  # every call to the model, with why it could not be used
