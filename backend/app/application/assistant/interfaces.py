from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.application.assistant.dtos import ChatRequest, ChatResponse, QueryResult, TurnRequest, WorkflowAnswer
from app.domain.assistant.conversation import (
    DEFAULT_MODE,
    AnswerDetails,
    AssistantMode,
    Conversation,
    Message,
    MessageRole,
    Rating,
    Turn,
)
from app.domain.assistant.memory import Memory, MemoryKind
from app.domain.assistant.names import KnownName, NameKind
from app.domain.assistant.prompt import UserNames
from app.domain.assistant.usage import TurnUsage
from app.domain.users.user import Gender


class SqlGuard(Protocol):
    def check(self, sql: str) -> str:
        """Return the SQL that may run (rebuilt from what was checked), or raise UnsafeQuery."""


class QueryRules(Protocol):
    """The answering rules for SQL that the guard already found safe."""

    def prepare(self, sql: str, names: UserNames, today: date) -> str:
        """Raise QueryRejected if the SQL breaks an answering rule (a loose or unknown name, the clock read
        directly); otherwise return it with CURRENT_DATE replaced by `today`."""

    def check_dates(self, sql: str, asked: str, today: date) -> None:
        """Raise QueryRejected if the SQL's dates were not asked for: only yesterday when `asked` (the earlier
        questions and the question) never names it, or last year's month when this year's has come and no year
        was mentioned."""

    def sizes_query(self, sql: str) -> str | None:
        """For a price comparison of one item between named shops: a query of the (vendor, size kind) pairs the
        item has there under the SQL's other conditions. None for any other SQL."""

    def size_hint(self, sql: str, result: QueryResult, sizes: QueryResult) -> str | None:
        """When the comparison's result misses a named shop and the item has a size kind at every one of them that
        the SQL left out: how to compare by it. Otherwise None."""

    def describe(self, sql: str) -> str | None:
        """What a query that ran looked at, for the line under its answer ("Looked at: laban at Spinneys, 1–31
        October 2026"), read from its conditions. None when any of them cannot be read, rather than a guess."""

    def sources_query(self, sql: str) -> str | None:
        """A query for the receipt_ids the result is based on, or None when it cannot be worked out reliably
        (a UNION, a WITH, or a subquery in FROM)."""

    def named_literals(self, sql: str) -> dict[str, set[str]]:
        """The names the SQL compares item_name, vendor and category with, as {"items": ..., "vendors": ...,
        "categories": ...}, so they can be checked against the user's data before `prepare`. Raises QueryRejected
        if the SQL does not parse."""


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


class StandardAssistant(Protocol):
    """The Standard mode's workflow: a hosted model with its own prompt and the app's read-only tools. It answers one
    question and returns the answer to save; the service saves it and ends the turn. It handles its own model and
    tool failures by returning an error answer; anything it raises fails the turn."""

    model: str  # the configured model, shown by GET /assistant/modes

    def answer(self, request: TurnRequest) -> WorkflowAnswer: ...


class StandardChatModel(Protocol):
    """The Standard mode's hosted model, called with native messages and tools. Raises ModelFailed when no usable
    response comes back (after the adapter's own bounded retries)."""

    model: str  # the configured model id

    def respond(self, request: ChatRequest) -> ChatResponse: ...


class NameRepository(Protocol):
    """The user's own vendor, item and category names, from all their confirmed receipts (no cap)."""

    def existing(self, kind: NameKind, names: Sequence[str]) -> set[str]:
        """Those of `names` that the user has, spelled exactly as given."""

    def inventory(self, kind: NameKind, limit: int) -> list[KnownName]:
        """Every name of that kind, most recently used first, at most `limit`."""

    def brands(self, limit: int) -> list[KnownName]:
        """Every brand on the user's items (lower case), most recently used first, at most `limit`."""


class MemoryRepository(Protocol):
    def list_all(self) -> list[Memory]:
        """Oldest first."""

    def count(self) -> int: ...

    def get(self, memory_id: int) -> Memory | None: ...

    def find_preference(self, memory_text: str) -> Memory | None:
        """The same preference, ignoring case and surrounding spaces."""

    def find_alias(self, alias: str) -> Memory | None:
        """The alias with this spelling, ignoring case and surrounding spaces."""

    def add(
        self,
        kind: MemoryKind,
        memory_text: str,
        source_conversation_id: int | None,
        source_message_id: int | None,
        alias: str | None = None,
        target_kind: NameKind | None = None,
        target_name: str | None = None,
        vendor_id: int | None = None,
    ) -> Memory | None:
        """None (and nothing saved) if the same preference or alias already exists."""

    def update(
        self, memory_id: int, memory_text: str, target_name: str | None = None, vendor_id: int | None = None
    ) -> Memory | None:
        """None if there is no such memory. A new `target_name` replaces the target and its vendor id."""

    def delete(self, memory_id: int) -> bool: ...


class UsageRepository(Protocol):
    """One record per question asked, kept when its conversation is deleted. The user's own records only, except
    the app-wide Standard total, which comes as two numbers."""

    def lock_standard_starts(self) -> None:
        """Make other Standard question starts wait until this transaction ends."""

    def reserve(self, turn_id: int, mode: AssistantMode) -> None: ...

    def finish(self, turn_id: int, outcome: str, usage: TurnUsage | None) -> None:
        """Only once: a record already finished is left as it is."""

    def count_since(self, mode: AssistantMode, period: str, time_zone: str) -> int:
        """The user's questions in `mode` since the start of today ("day") or this month ("month") in the zone."""

    def standard_month_spending(self, time_zone: str) -> tuple[Decimal, int]:
        """Every user's Standard spending this month: the known estimates, and how many have no estimate yet."""


class ProfileRepository(Protocol):
    def gender(self) -> Gender | None:
        """The gender the signed-in user chose at sign-up (None for accounts made before it was asked)."""


class ConversationRepository(Protocol):
    def create(self, title: str, mode: AssistantMode = DEFAULT_MODE) -> int: ...

    def exists(self, conversation_id: int) -> bool: ...

    def mode_of(self, conversation_id: int) -> AssistantMode | None:
        """None if there is no such conversation for this user."""

    def hold(self, conversation_id: int) -> bool:
        """Keep the conversation from being deleted until this transaction ends. False if it no longer exists."""

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

    def get(self, message_id: int) -> Message | None:
        """With its current rating. None if there is no such message for this user."""

    def role_of(self, message_id: int) -> MessageRole | None:
        """None if there is no such message for this user."""


class FeedbackRepository(Protocol):
    def set(self, message_id: int, rating: Rating) -> None:
        """Create or replace the rating of an assistant answer."""

    def clear(self, message_id: int) -> bool: ...


class TurnRepository(Protocol):
    """Answering one question. The database enforces that a conversation has at most one running turn, that a key
    is used once per user, and that only a running turn can complete or fail."""

    def start(
        self, conversation_id: int, question_message_id: int, mode: AssistantMode, idempotency_key: str | None
    ) -> int | None:
        """A new running turn's id, or None when the conversation already has a running turn or the key was used
        (by a request that may have committed only just now)."""

    def give_up_abandoned(self, conversation_id: int, older_than_seconds: float) -> int:
        """Mark the conversation's running turn failed ("abandoned") if it started longer ago than that: its
        worker stopped or hung. Returns how many were given up (0 or 1)."""

    def find_by_key(self, idempotency_key: str) -> Turn | None: ...

    def get(self, turn_id: int) -> Turn | None: ...

    def complete(self, turn_id: int, answer_message_id: int, execution: dict | None = None) -> bool:
        """False (and nothing changes) if the turn is no longer running or no longer exists."""

    def fail(self, turn_id: int, problem: str) -> bool:
        """False (and nothing changes) if the turn is no longer running or no longer exists."""

    def previous_execution(self, conversation_id: int, turn_id: int) -> dict | None:
        """The execution record of the conversation's turn just before `turn_id`, if that turn was answered; None
        when there is none, or it failed (its answer was never shown)."""
