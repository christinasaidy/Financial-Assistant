from app.application.assistant.dtos import (
    ConversationView,
    MessageView,
    QueryResult,
    SavedQuestion,
    SourceReceipt,
)
from app.application.assistant.interfaces import ReadOnlyQueryRunner, SqlGuard
from app.application.shared.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.domain.assistant.conversation import (
    AnswerDetails,
    Conversation,
    Message,
    MessageRole,
    Rating,
    clean_question,
    title_from,
)
from app.domain.assistant.errors import CannotRateQuestion, ConversationNotFound, MessageNotFound


class AssistantService:
    """Answers spending questions and keeps the conversations they belong to.

    The question flow (question -> SQL -> answer, phase 3) is built on `save_question`, `run_query`
    and `save_answer`; the rest is what the conversation screens need.
    """

    def __init__(self, uow: UnitOfWorkFactory, guard: SqlGuard, runner: ReadOnlyQueryRunner) -> None:
        self._uow = uow
        self._guard = guard
        self._runner = runner

    # --- running generated SQL ---

    def run_query(self, user_id: int, sql: str) -> QueryResult:
        """Check generated SQL, then run it as the read-only role, limited to this user's rows.
        Two independent layers: the guard refuses anything unsafe, and the database role could
        not do harm even if something got past it."""
        return self._runner.run(user_id, self._guard.check(sql))

    # --- saving a question and its answer (used by the question flow) ---

    def save_question(self, user_id: int, conversation_id: int | None, question: str) -> SavedQuestion:
        """Save a question. Without a conversation id, it starts a new conversation named after it."""
        question = clean_question(question)
        with self._uow(user_id) as work:
            if conversation_id is None:
                conversation_id = work.conversations.create(title_from(question))
            elif not work.conversations.exists(conversation_id):
                raise ConversationNotFound
            message = work.messages.add(conversation_id, MessageRole.USER, question)
        return SavedQuestion(conversation_id=conversation_id, message_id=message.id)

    def save_answer(self, user_id: int, conversation_id: int, content: str, details: AnswerDetails) -> MessageView:
        """Save an assistant answer with its details (kept whether or not it is ever rated)."""
        with self._uow(user_id) as work:
            if not work.conversations.exists(conversation_id):
                raise ConversationNotFound
            message = work.messages.add(conversation_id, MessageRole.ASSISTANT, content, details)
            return self._view(work, message)

    # --- the conversation screens ---

    def list_conversations(self, user_id: int) -> list[Conversation]:
        """Newest activity first."""
        with self._uow(user_id) as work:
            return work.conversations.list_all()

    def open_conversation(self, user_id: int, conversation_id: int) -> ConversationView:
        """Every message exactly as it was saved. Answers are not recalculated; receipts deleted since
        are reported as unavailable."""
        with self._uow(user_id) as work:
            conversation = work.conversations.get(conversation_id)
            if conversation is None:
                raise ConversationNotFound
            messages = work.messages.list_for(conversation_id)
            cited = {receipt_id for m in messages if m.details for receipt_id in m.details.receipt_ids}
            still_there = work.receipts.existing_ids(sorted(cited))
            views = [self._view(work, message, still_there) for message in messages]
        return ConversationView(conversation=conversation, messages=views)

    def delete_conversation(self, user_id: int, conversation_id: int) -> None:
        """Its messages and ratings are deleted with it. Receipts are not touched."""
        with self._uow(user_id) as work:
            if not work.conversations.delete(conversation_id):
                raise ConversationNotFound

    def rate(self, user_id: int, message_id: int, rating: Rating | None) -> None:
        """Rate an assistant answer up or down, change the rating, or remove it (None)."""
        with self._uow(user_id) as work:
            role = work.messages.role_of(message_id)
            if role is None:
                raise MessageNotFound
            if role is not MessageRole.ASSISTANT:
                raise CannotRateQuestion
            if rating is None:
                work.feedback.clear(message_id)
            else:
                work.feedback.set(message_id, rating)

    @staticmethod
    def _view(work: UnitOfWork, message: Message, still_there: set[int] | None = None) -> MessageView:
        receipt_ids = message.details.receipt_ids if message.details else ()
        if still_there is None:
            still_there = work.receipts.existing_ids(list(receipt_ids))
        return MessageView(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            details=message.details,
            source_receipts=[SourceReceipt(receipt_id, receipt_id in still_there) for receipt_id in receipt_ids],
            rating=message.rating,
        )
