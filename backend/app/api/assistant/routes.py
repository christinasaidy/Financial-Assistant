"""Conversation screens. Asking a question arrives with the question flow (phase 3)."""

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
    kind: str | None  # assistant answers: answer, clarify, unsupported or error
    sql: str | None  # the query that ran, for "show query"
    source_receipts: list[SourceReceiptOut]
    rating: str | None  # "up", "down" or none

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
        )


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class RatingIn(BaseModel):
    rating: Literal["up", "down"]


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
