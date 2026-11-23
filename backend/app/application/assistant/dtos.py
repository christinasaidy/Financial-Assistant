from dataclasses import dataclass
from datetime import datetime

from app.domain.assistant.answer import ModelReply
from app.domain.assistant.conversation import (
    DEFAULT_MODE,
    AnswerDetails,
    AssistantMode,
    Attempt,
    Conversation,
    Message,
    MessageRole,
    Rating,
)


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
    understood: str | None = None  # what the query looked at, worked out from its SQL (answers only)


@dataclass(frozen=True)
class ConversationView:
    conversation: Conversation
    messages: list[MessageView]


@dataclass(frozen=True)
class AskResult:
    conversation_id: int  # the new conversation's id when the question started one
    answer: MessageView
    mode: AssistantMode = DEFAULT_MODE  # the mode that answered (the conversation's)


@dataclass(frozen=True)
class QuestionOutcome:
    """What the SQL step came to (`AssistantService.run_question`). At most one of `result` and `reply` is set;
    neither means both attempts failed or the model could not be reached."""

    result: QueryResult | None  # the query's result, when the model wrote usable SQL
    reply: ModelReply | None  # or its clarifying question, refusal or short reply
    attempts: tuple[Attempt, ...]  # every call to the model, with why it could not be used


@dataclass(frozen=True)
class TurnRequest:
    """One question for the Standard workflow, with what the app already knows. The user comes from the signed-in
    request, never from the model."""

    user_id: int
    conversation_id: int
    turn_id: int
    question: str  # already cleaned
    history: tuple[Message, ...]  # the conversation's saved messages before this question, oldest first
    receipts_waiting: int  # receipts waiting for review, which no answer counts yet


@dataclass(frozen=True)
class WorkflowAnswer:
    content: str  # what the user is shown
    details: AnswerDetails  # saved with the answer, as for every assistant message
    execution: dict | None = None  # internal record of how it was answered, kept on the turn; never sent to clients


@dataclass(frozen=True)
class ModeStatus:
    """Whether a mode is set up on this server. `available` means configured (a key and a model), not that the
    provider was reached: no call is made to find out."""

    mode: AssistantMode
    available: bool
    models: tuple[str, ...]
