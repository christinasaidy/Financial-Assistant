import logging
import time
from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal

from app.application.assistant.dtos import (
    AskResult,
    ConversationView,
    MessageView,
    QueryResult,
    QuestionOutcome,
    SavedQuestion,
    SourceReceipt,
)
from app.application.assistant.interfaces import AssistantModel, QueryRules, ReadOnlyQueryRunner, SqlGuard
from app.application.shared.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.domain.assistant import answer as answers
from app.domain.assistant.answer import ReplyForm
from app.domain.assistant.conversation import (
    AnswerDetails,
    AnswerKind,
    Attempt,
    Conversation,
    Message,
    MessageRole,
    Rating,
    Step,
    clean_question,
    title_from,
)
from app.domain.assistant.errors import (
    CannotRateQuestion,
    ConversationNotFound,
    MessageNotFound,
    ModelFailed,
    ModelUnavailable,
    QueryFailed,
    QueryRejected,
    UnsafeQuery,
    UnusableReply,
)
from app.domain.assistant.prompt import (
    VIEW_CATEGORIES,
    Exchange,
    UserNames,
    answer_repair_prompt,
    build_answer_prompt,
    build_prompt,
    recent_exchanges,
    repair_prompt,
)
from app.domain.receipts.normalization import MAX_NAME_WORDS, names_for_prompt
from app.domain.receipts.status import ReceiptStatus

logger = logging.getLogger(__name__)

ITEM_NAMES_LIMIT = 200  # the same list receipt reading offers the vision model
VENDOR_NAMES_LIMIT = 100
ATTEMPTS_PER_STEP = 2  # the first try and one repair
DEFAULT_HISTORY_EXCHANGES = 6
DEFAULT_HISTORY_CHARACTERS = 6000


class AssistantService:
    """Answers spending questions and keeps the conversations they belong to.

    The question flow (`ask`, phase 3) is built on `save_question`, `run_query` and `save_answer`; the rest is
    what the conversation screens need.
    """

    def __init__(
        self,
        uow: UnitOfWorkFactory,
        guard: SqlGuard,
        runner: ReadOnlyQueryRunner,
        rules: QueryRules,
        model: AssistantModel,
        today: Callable[[], date] = date.today,
        history_exchanges: int = DEFAULT_HISTORY_EXCHANGES,
        history_characters: int = DEFAULT_HISTORY_CHARACTERS,
    ) -> None:
        self._uow = uow
        self._guard = guard
        self._runner = runner
        self._rules = rules
        self._model = model
        self._today = today
        self._history_exchanges = history_exchanges
        self._history_characters = history_characters

    # --- answering a question (decisions approved by the user on 2026-11-03) ---

    def ask(self, user_id: int, conversation_id: int | None, question: str) -> AskResult:
        """Answer a question and save both, in a new conversation if no id is given.

        The question is saved first, on its own, so it is kept even if answering fails. Then: the model writes SQL
        (or asks, refuses or replies), the guard and the answering rules check it, it runs as the read-only role,
        the model writes the answer from the result and every number in it is checked against that result. Each
        model step gets one second attempt, told what was wrong with the first."""
        saved = self.save_question(user_id, conversation_id, question)
        question = clean_question(question)
        with self._uow(user_id) as work:
            history = recent_exchanges(
                work.messages.list_for(saved.conversation_id), self._history_exchanges, self._history_characters
            )
            waiting = work.receipts.count_with_status(ReceiptStatus.NEEDS_REVIEW)
        content, details = self._answer(user_id, question, history, waiting)
        return AskResult(saved.conversation_id, self.save_answer(user_id, saved.conversation_id, content, details))

    def run_question(self, user_id: int, question: str, history: Sequence[Exchange] = ()) -> QuestionOutcome:
        """The SQL step on its own: the model turns the question into SQL (or asks, refuses or replies), the guard
        and the answering rules check it, and it runs as the read-only role, with one repair. Nothing is saved.

        `ask` answers with it, and the research evaluation scores it, so both always run exactly the same step.
        Raises ModelUnavailable if no model is configured."""
        question = clean_question(question)
        with self._uow(user_id) as work:
            names = UserNames(
                items=names_for_prompt(work.receipts.known_item_names(ITEM_NAMES_LIMIT, MAX_NAME_WORDS),
                                       ITEM_NAMES_LIMIT),
                vendors=work.vendors.recent_names(VENDOR_NAMES_LIMIT),
                categories=[category.name for category in work.categories.list_all()] + list(VIEW_CATEGORIES),
            )  # fmt: skip
        attempts: list[Attempt] = []
        outcome = self._write_sql(user_id, question, names, list(history), attempts)
        return QuestionOutcome(
            result=outcome if isinstance(outcome, QueryResult) else None,
            reply=outcome if isinstance(outcome, answers.ModelReply) else None,
            attempts=tuple(attempts),
        )

    def _answer(
        self, user_id: int, question: str, history: list[Exchange], waiting: int
    ) -> tuple[str, AnswerDetails]:
        started = time.perf_counter()
        attempts: list[Attempt] = []

        def finished(kind: AnswerKind, content: str, **found: object) -> tuple[str, AnswerDetails]:
            if kind is AnswerKind.ANSWER and waiting:  # receipts not confirmed yet are not counted: say so
                content = f"{content} {answers.review_note(waiting)}"
            duration_ms = round((time.perf_counter() - started) * 1000)
            return content, AnswerDetails(kind, attempts=tuple(attempts), duration_ms=duration_ms, **found)

        try:
            outcome = self.run_question(user_id, question, history)
        except ModelUnavailable:
            return finished(AnswerKind.ERROR, answers.NOT_AVAILABLE)
        attempts.extend(outcome.attempts)
        if outcome.reply is not None:
            if outcome.reply.form is ReplyForm.UNSUPPORTED:
                return finished(AnswerKind.UNSUPPORTED, answers.UNSUPPORTED)
            kind = AnswerKind.CLARIFY if outcome.reply.form is ReplyForm.CLARIFY else AnswerKind.REPLY
            return finished(kind, outcome.reply.text)
        if outcome.result is None:
            return finished(AnswerKind.ERROR, answers.FAILURE)

        result = outcome.result
        if answers.is_empty_result(result.rows):  # nothing matched: no need to ask the model to say so
            return finished(AnswerKind.ANSWER, answers.NO_MATCHES, sql=result.sql, row_count=len(result.rows))
        receipt_ids = self._sources(user_id, result.sql)
        text = self._write_answer(question, result, receipt_ids, attempts)
        found: dict[str, object] = {"sql": result.sql, "receipt_ids": receipt_ids or (), "row_count": len(result.rows)}
        if text is None:  # no answer passed the number check: show the result itself
            text = answers.TABLE_INTRO
            found |= {"columns": tuple(result.columns), "rows": answers.as_text(result.rows)}
        return finished(AnswerKind.ANSWER, text, **found)

    def _write_sql(
        self, user_id: int, question: str, names: UserNames, history: list[Exchange], attempts: list[Attempt]
    ) -> QueryResult | answers.ModelReply | None:
        """The query's result, or the model's clarifying question, refusal or reply. None if both attempts failed
        or the model could not be reached (it already waited and retried once by then)."""
        today = self._today()  # one date for the prompt and for CURRENT_DATE, so they can never disagree
        prompt = build_prompt(question, names, today, history)
        current = prompt
        for _ in range(ATTEMPTS_PER_STEP):
            output = None
            try:
                output = self._model.write_sql(current)
                reply = answers.read_reply(output)
                if reply.form is ReplyForm.SQL:
                    sql = self._rules.prepare(self._guard.check(reply.text), names, today)
                    outcome: QueryResult | answers.ModelReply = self.run_query(user_id, sql)
                else:
                    answers.check_numbers(reply.text, answers.numbers_in(question), "the question")
                    outcome = reply
            except ModelUnavailable:
                raise
            except ModelFailed as exc:
                attempts.append(Attempt(Step.SQL, self._model.sql_model, None, str(exc)))
                return None
            except (UnusableReply, UnsafeQuery, QueryRejected, QueryFailed) as exc:
                attempts.append(Attempt(Step.SQL, self._model.sql_model, output, str(exc)))
                current = repair_prompt(prompt, output, str(exc))
                continue
            attempts.append(Attempt(Step.SQL, self._model.sql_model, output))
            return outcome
        return None

    def _sources(self, user_id: int, sql: str) -> tuple[int, ...] | None:
        """The receipts the result is based on (at most the runner's row limit), or None if that cannot be told."""
        query = self._rules.sources_query(sql)
        if query is None:
            return None
        try:
            result = self.run_query(user_id, query)
        except (UnsafeQuery, QueryFailed) as exc:
            logger.warning("The source receipts of an answer could not be found: %s", exc)
            return None
        return tuple(int(row[0]) for row in result.rows if row[0] is not None)

    def _write_answer(
        self, question: str, result: QueryResult, receipt_ids: tuple[int, ...] | None, attempts: list[Attempt]
    ) -> str | None:
        """The model's answer, once every number in it is found in the result. None if both attempts failed."""
        today = self._today()
        totals = answers.column_totals(result.columns, result.rows)
        prompt = build_answer_prompt(
            question,
            result.columns,
            result.rows,
            {name: total for name, total in totals.items() if name.endswith("_usd")},  # the combined USD total
            None if receipt_ids is None else len(receipt_ids),
            result.truncated,
            today,
        )
        allowed = [
            *answers.result_numbers(result.rows),
            *totals.values(),
            *answers.date_numbers(today),
            Decimal(len(result.rows)),
            *([Decimal(len(receipt_ids))] if receipt_ids is not None else []),
            *answers.numbers_in(question),
            *answers.numbers_in(result.sql),
        ]
        current = prompt
        for _ in range(ATTEMPTS_PER_STEP):
            output = None
            try:
                output = self._model.write_answer(current)
                text = (output or "").strip()
                if not text:
                    raise UnusableReply("The answer is empty")
                answers.check_numbers(text, allowed, "the result")
            except ModelFailed as exc:
                attempts.append(Attempt(Step.ANSWER, self._model.answer_model, None, str(exc)))
                return None
            except UnusableReply as exc:
                attempts.append(Attempt(Step.ANSWER, self._model.answer_model, output, str(exc)))
                current = answer_repair_prompt(prompt, output, str(exc))
                continue
            attempts.append(Attempt(Step.ANSWER, self._model.answer_model, output))
            return text
        return None

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
