"""Assistant conversations (decisions agreed with the user on 2026-10-15).

- A conversation starts with its first question; there are no empty conversations. Its title is that
  question, cut to 60 characters with an ellipsis if needed.
- Each assistant answer keeps its details (kind, the SQL that ran, the receipts it was based on, row count,
  duration) whether or not it is ever rated.
- Reopening shows saved answers exactly as they were; receipts deleted since are reported as unavailable.
- Since the question flow (phase 3, 2026-11-03), the details also keep every attempt the model made and, for an
  answer shown as a table, its columns and rows (so a reopened chat can draw it again).
- One rating (up or down) per assistant answer, which can be changed or removed. Questions cannot be rated.
- Since the two assistant modes (2026-11-23), each conversation keeps the mode it was started in (`standard` or
  `beta`), and every question it is asked is answered in that mode: a conversation never switches models half way.
  Conversations from before then are `beta`, the SQL workflow they were answered with; the models that actually
  answered them (Gemini, during development) stay in each answer's attempts.
- Each question is answered in one turn: started when the question is saved, then completed (its answer saved) or
  failed. At most one turn of a conversation runs at a time.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain.assistant.errors import InvalidIdempotencyKey, InvalidQuestion

TITLE_LENGTH = 60
MAX_QUESTION_LENGTH = 1000


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class AssistantMode(StrEnum):
    """Which assistant answers a conversation. The same conversations, data rules and safety checks serve both;
    the models, prompts and workflows are separate."""

    STANDARD = "standard"  # a hosted model (Anthropic's Claude Sonnet) that calls the app's read-only tools
    BETA = "beta"  # the fine-tuned model's workflow: question -> SQL -> checks -> answer (the original assistant)


# What a new conversation is answered with when the client does not say. The original workflow, so a client written
# before the modes never starts a paid hosted-model conversation without choosing it.
DEFAULT_MODE = AssistantMode.BETA


class TurnStatus(StrEnum):
    RUNNING = "running"  # the question is saved and being answered
    COMPLETED = "completed"  # its answer is saved
    FAILED = "failed"  # answering stopped without an answer (a crash, or abandoned after a restart)


class AnswerKind(StrEnum):
    ANSWER = "answer"  # a normal answer from data
    CLARIFY = "clarify"  # the assistant asks a clarifying question
    UNSUPPORTED = "unsupported"  # "I can't answer that"
    REPLY = "reply"  # a short reply that needs no data ("hi", "thanks", "what can you do")
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


class Step(StrEnum):
    SQL = "sql"  # the model writes the query (or asks, refuses, replies)
    ANSWER = "answer"  # the model writes the answer from the query's result


@dataclass(frozen=True)
class Attempt:
    """One call to the model while answering, kept for error analysis."""

    step: Step
    model: str
    output: str | None  # what the model returned; None if the call itself failed
    problem: str | None = None  # why it could not be used; None if it was used


@dataclass(frozen=True)
class AnswerDetails:
    """Saved with every assistant answer, so it can be checked and reopened later."""

    kind: AnswerKind
    sql: str | None = None
    receipt_ids: tuple[int, ...] = ()
    row_count: int | None = None
    duration_ms: int | None = None
    attempts: tuple[Attempt, ...] = ()
    # Only for an answer shown as a table: the result as text, exactly as it was shown.
    columns: tuple[str, ...] | None = None
    rows: tuple[tuple[str | None, ...], ...] | None = None


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
    mode: AssistantMode = DEFAULT_MODE


@dataclass(frozen=True)
class Turn:
    """Answering one question: from the moment it is saved until its answer is saved, or answering fails."""

    id: int
    conversation_id: int
    question_message_id: int
    question: str  # the question's text, so a repeated request can be checked against it
    mode: AssistantMode
    status: TurnStatus
    answer_message_id: int | None = None
    idempotency_key: str | None = None
    problem: str | None = None  # why it failed


MAX_IDEMPOTENCY_KEY_LENGTH = 200


def clean_idempotency_key(raw: str | None) -> str | None:
    """A client's key for one ask, so a retried request is answered once. None when no key was sent."""
    if raw is None:
        return None
    key = raw.strip()
    if not key or len(key) > MAX_IDEMPOTENCY_KEY_LENGTH or not key.isprintable():
        raise InvalidIdempotencyKey(f"An Idempotency-Key must be 1 to {MAX_IDEMPOTENCY_KEY_LENGTH} printable characters")
    return key


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
