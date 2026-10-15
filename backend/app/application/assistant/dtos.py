from dataclasses import dataclass
from datetime import datetime

from app.domain.assistant.conversation import AnswerDetails, Conversation, MessageRole, Rating


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
