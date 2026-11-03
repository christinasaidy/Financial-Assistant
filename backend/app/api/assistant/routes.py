"""Asking questions (phase 3) and the conversation screens."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.api.container import Container
from app.api.dependencies import get_container, get_current_user_id
from app.application.assistant.dtos import MessageView
from app.domain.assistant.conversation import Conversation, Rating

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    last_message_at: datetime
    message_count: int

    @classmethod
    def from_conversation(cls, conversation: Conversation) -> "ConversationOut":
        return cls(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            last_message_at=conversation.last_message_at,
            message_count=conversation.message_count,
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
    # Only when the answer is shown as a table (no sentence passed the number check): the result, as text.
    columns: list[str] | None = None
    rows: list[list[str | None]] | None = None

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
            columns=list(details.columns) if details and details.columns is not None else None,
            rows=[list(row) for row in details.rows] if details and details.rows is not None else None,
        )


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class RatingIn(BaseModel):
    rating: Literal["up", "down"]


class AskIn(BaseModel):
    question: str
    conversation_id: int | None = None  # leave out to start a new conversation


class AnswerOut(MessageOut):
    conversation_id: int  # the new conversation's id when none was given, for the follow-up questions


@router.post("/ask", response_model=AnswerOut)
def ask(
    body: AskIn, user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)
) -> AnswerOut:
    """Answer a question and return the saved answer. Waits for the answer (a few seconds); no streaming."""
    result = container.assistant.ask(user_id, body.conversation_id, body.question)
    return AnswerOut(**MessageOut.from_view(result.answer).model_dump(), conversation_id=result.conversation_id)


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
