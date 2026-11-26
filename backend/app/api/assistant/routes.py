"""Asking questions (phase 3) and the conversation screens."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel

from app.api.container import Container
from app.api.dependencies import get_container, get_current_user_id
from app.application.assistant.dtos import MessageView
from app.domain.assistant.conversation import AssistantMode, Conversation, Rating

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    last_message_at: datetime
    message_count: int
    assistant_mode: str  # "standard" or "beta": every answer in the conversation comes from this mode

    @classmethod
    def from_conversation(cls, conversation: Conversation) -> "ConversationOut":
        return cls(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            last_message_at=conversation.last_message_at,
            message_count=conversation.message_count,
            assistant_mode=conversation.mode.value,
        )


class SourceReceiptOut(BaseModel):
    receipt_id: int
    available: bool  # False once the receipt has been deleted


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    kind: str | None  # assistant answers: answer, clarify, unsupported, reply or error
    sql: str | None  # the query that ran, for "show query"
    source_receipts: list[SourceReceiptOut]
    rating: str | None  # "up", "down" or none
    understood: str | None = None  # answers: what the query looked at, from its SQL ("Looked at: ...")
    # Only when the answer is shown as a table (no sentence passed the number check): the result, as text.
    columns: list[str] | None = None
    rows: list[list[str | None]] | None = None
    # Answers: the models that were called for it, as saved (so an old Gemini answer is never shown as another's).
    models: list[str] = []

    @classmethod
    def from_view(cls, message: MessageView) -> "MessageOut":
        details = message.details
        return cls(
            id=message.id,
            role=message.role.value,
            content=message.content,
            created_at=message.created_at,
            kind=details.kind.value if details else None,
            sql=details.sql if details else None,
            source_receipts=[SourceReceiptOut(**vars(source)) for source in message.source_receipts],
            rating=message.rating.value if message.rating else None,
            understood=message.understood,
            columns=list(details.columns) if details and details.columns is not None else None,
            rows=[list(row) for row in details.rows] if details and details.rows is not None else None,
            models=list(dict.fromkeys(attempt.model for attempt in details.attempts)) if details else [],
        )


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class RatingIn(BaseModel):
    rating: Literal["up", "down"]


class AskIn(BaseModel):
    question: str
    conversation_id: int | None = None  # leave out to start a new conversation
    # For a new conversation: which assistant answers it ("beta" when left out, the original workflow). For an
    # existing one it may be left out; a different mode than the conversation's is refused (409).
    assistant_mode: Literal["standard", "beta"] | None = None


class AnswerOut(MessageOut):
    conversation_id: int  # the new conversation's id when none was given, for the follow-up questions
    assistant_mode: str  # the mode that answered: the conversation's


class ModeOut(BaseModel):
    mode: str
    available: bool  # configured on this server (a key and a model); not a live check of the provider
    models: list[str]
    reason: str | None = None  # when unavailable: not_configured, daily_limit (this user) or monthly_cap (the app)


class UsageCountsOut(BaseModel):
    standard: int
    beta: int


class UsageOut(BaseModel):
    """The signed-in user's own questions; never anyone else's, and no tokens or costs."""

    today: UsageCountsOut
    this_month: UsageCountsOut
    standard_daily_limit: int | None
    standard_left_today: int | None


@router.post("/ask", response_model=AnswerOut)
def ask(
    body: AskIn,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AnswerOut:
    """Answer a question and return the saved answer. Waits for the answer; no streaming.

    Send a new `Idempotency-Key` header (any unique string, e.g. a UUID) with each question: if the request is
    retried with the same key, the first answer is returned instead of answering twice. 409 while the conversation
    is still answering an earlier question; nothing is saved then."""
    mode = AssistantMode(body.assistant_mode) if body.assistant_mode else None
    result = container.assistant.ask(
        user_id, body.conversation_id, body.question, mode=mode, idempotency_key=idempotency_key
    )
    return AnswerOut(
        **MessageOut.from_view(result.answer).model_dump(),
        conversation_id=result.conversation_id,
        assistant_mode=result.mode.value,
    )


@router.get("/modes", response_model=list[ModeOut])
def list_modes(
    user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)
) -> list[ModeOut]:
    """The assistant modes and whether each can answer this user now, for the mode picker."""
    modes = container.assistant.modes(user_id)
    return [ModeOut(mode=m.mode.value, available=m.available, models=list(m.models), reason=m.reason) for m in modes]


@router.get("/usage", response_model=UsageOut)
def my_usage(user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)) -> UsageOut:
    usage = container.assistant.usage(user_id)

    def counts(by_mode) -> UsageCountsOut:
        return UsageCountsOut(standard=by_mode[AssistantMode.STANDARD], beta=by_mode[AssistantMode.BETA])

    return UsageOut(today=counts(usage.today), this_month=counts(usage.this_month),
                    standard_daily_limit=usage.standard_daily_limit, standard_left_today=usage.standard_left_today)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)
) -> list[ConversationOut]:
    """Newest activity first."""
    return [ConversationOut.from_conversation(c) for c in container.assistant.list_conversations(user_id)]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def open_conversation(
    conversation_id: int,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> ConversationDetailOut:
    """Every message exactly as it was saved; answers are earlier answers, not recalculated."""
    view = container.assistant.open_conversation(user_id, conversation_id)
    return ConversationDetailOut(
        **ConversationOut.from_conversation(view.conversation).model_dump(),
        messages=[MessageOut.from_view(message) for message in view.messages],
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> Response:
    container.assistant.delete_conversation(user_id, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/messages/{message_id}/rating", status_code=status.HTTP_204_NO_CONTENT)
def rate_answer(
    message_id: int,
    body: RatingIn,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> Response:
    """Rate an assistant answer up or down, or change the rating."""
    container.assistant.rate(user_id, message_id, Rating(body.rating))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/messages/{message_id}/rating", status_code=status.HTTP_204_NO_CONTENT)
def remove_rating(
    message_id: int,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> Response:
    container.assistant.rate(user_id, message_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
