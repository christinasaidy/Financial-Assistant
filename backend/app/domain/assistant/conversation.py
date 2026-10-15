"""Assistant conversations (decisions agreed with the user on 2026-10-15).

- A conversation starts with its first question; there are no empty conversations. Its title is that
  question, cut to 60 characters with an ellipsis if needed.
- Each assistant answer keeps its details (kind, the SQL that ran, the receipts it was based on, row count,
  duration) whether or not it is ever rated.
- Reopening shows saved answers exactly as they were; receipts deleted since are reported as unavailable.
- One rating (up or down) per assistant answer, which can be changed or removed. Questions cannot be rated.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain.assistant.errors import InvalidQuestion

TITLE_LENGTH = 60
MAX_QUESTION_LENGTH = 1000


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class AnswerKind(StrEnum):
    ANSWER = "answer"  # a normal answer from data
    CLARIFY = "clarify"  # the assistant asks a clarifying question
    UNSUPPORTED = "unsupported"  # "I can't answer that"
    ERROR = "error"  # something went wrong while answering


class Rating(StrEnum):
    UP = "up"
    DOWN = "down"

    @property
    def score(self) -> int:  # how it is stored: 1 or -1
        return 1 if self is Rating.UP else -1

    @classmethod
    def from_score(cls, score: int) -> "Rating":
        return cls.UP if score > 0 else cls.DOWN


@dataclass(frozen=True)
class AnswerDetails:
    """Saved with every assistant answer, so it can be checked and reopened later."""

    kind: AnswerKind
    sql: str | None = None
    receipt_ids: tuple[int, ...] = ()
    row_count: int | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class Message:
    id: int
    role: MessageRole
    content: str
    created_at: datetime
    details: AnswerDetails | None = None  # assistant answers only
    rating: Rating | None = None  # assistant answers only


@dataclass(frozen=True)
class Conversation:
    id: int
    title: str
    created_at: datetime
    last_message_at: datetime
    message_count: int
    messages: tuple[Message, ...] = field(default=())


def clean_question(raw: str) -> str:
    question = " ".join(raw.split())
    if not question:
        raise InvalidQuestion("Type a question")
    if len(question) > MAX_QUESTION_LENGTH:
        raise InvalidQuestion(f"Questions can be at most {MAX_QUESTION_LENGTH} characters")
    return question


def title_from(question: str) -> str:
    """The first question, cut to 60 characters (ending in an ellipsis) if it is longer."""
    question = clean_question(question)
    if len(question) <= TITLE_LENGTH:
        return question
    return question[: TITLE_LENGTH - 1].rstrip() + "…"
