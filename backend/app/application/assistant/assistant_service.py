import logging
import time
from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal

from app.application.assistant.dtos import (
    AskResult,
    ConversationView,
    MessageView,
    ModeStatus,
    QueryResult,
    QuestionOutcome,
    SavedQuestion,
    SourceReceipt,
    TurnRequest,
    UsageView,
    WorkflowAnswer,
    budget_proposals,
)
from app.application.assistant.interfaces import (
    AssistantModel,
    QueryRules,
    ReadOnlyQueryRunner,
    SqlGuard,
    StandardAssistant,
)
from app.application.shared.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.domain.assistant import answer as answers
from app.domain.assistant.answer import ReplyForm
from app.domain.assistant.arabizi import address_for
from app.domain.assistant.conversation import (
    DEFAULT_MODE,
    AnswerDetails,
    AnswerKind,
    AssistantMode,
    Attempt,
    Conversation,
    Message,
    MessageRole,
    Rating,
    Step,
    Turn,
    TurnStatus,
    clean_idempotency_key,
    clean_question,
    title_from,
)
from app.domain.assistant.errors import (
    AssistantModeConflict,
    CannotRateQuestion,
    ConversationNotFound,
    DailyLimitReached,
    IdempotencyKeyReused,
    MessageNotFound,
    ModelFailed,
    ModelUnavailable,
    QueryFailed,
    QueryRejected,
    TurnInProgress,
    TurnSuperseded,
    UnsafeQuery,
    UnusableReply,
)
from app.domain.assistant.prompt import (
    VIEW_CATEGORIES,
    Exchange,
    Gender,
    UserNames,
    answer_repair_prompt,
    build_answer_prompt,
    build_prompt,
    recent_exchanges,
    repair_prompt,
)
from app.domain.assistant.usage import StandardQuota, TurnUsage, over_cap
from app.domain.receipts.normalization import MAX_NAME_WORDS, names_for_prompt
from app.domain.receipts.status import ReceiptStatus

logger = logging.getLogger(__name__)

ITEM_NAMES_LIMIT = 200  # the same list receipt reading offers the vision model
VENDOR_NAMES_LIMIT = 100
ATTEMPTS_PER_STEP = 2  # the first try and one repair
DEFAULT_HISTORY_EXCHANGES = 6
DEFAULT_HISTORY_CHARACTERS = 6000
# A turn still running after this long is taken to be abandoned (its worker stopped or hung) and given up, so the
# conversation can be asked again. Above the Beta workflow's worst case: four model calls, each up to twice 60 s.
DEFAULT_TURN_TIMEOUT_SECONDS = 900.0
DEFAULT_TIME_ZONE = "Asia/Beirut"  # whose days and months the usage counts are in, without a quota


class AssistantService:
    """Answers spending questions and keeps the conversations they belong to.

    `ask` answers a question in its conversation's mode: Beta (the fine-tuned model's SQL workflow, below) or
    Standard (a separate workflow, injected). Both share the conversations, the turn rules and the saved answers.
    `save_question` and `save_answer` save one message each, for tests and tools; the rest is what the
    conversation screens need.
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
        *,
        standard: StandardAssistant | None = None,
        beta_available: bool = True,
        turn_timeout_seconds: float = DEFAULT_TURN_TIMEOUT_SECONDS,
        standard_quota: StandardQuota | None = None,
    ) -> None:
        """The positional arguments are the Beta workflow's (the research evaluation builds the service with them
        alone). `standard` is the Standard workflow, None when it is not configured: its conversations are then
        answered "not available", exactly as Beta's are without a model; neither mode ever answers for the other.
        `beta_available` only says whether Beta's model is configured, for `modes()`. `standard_quota` holds the
        Standard limits (None: no limits)."""
        self._uow = uow
        self._guard = guard
        self._runner = runner
        self._rules = rules
        self._model = model
        self._today = today
        self._history_exchanges = history_exchanges
        self._history_characters = history_characters
        self._standard = standard
        self._beta_available = beta_available
        self._turn_timeout = turn_timeout_seconds
        self._quota = standard_quota

    # --- answering a question (decisions approved by the user on 2026-11-03) ---

    def ask(
        self,
        user_id: int,
        conversation_id: int | None,
        question: str,
        *,
        mode: AssistantMode | None = None,
        idempotency_key: str | None = None,
    ) -> AskResult:
        """Answer a question and save both, in a new conversation if no id is given.

        A new conversation is answered in `mode` (the original Beta workflow when it is not given). A conversation
        keeps its mode: `mode` may be left out for it, and a different one is refused before anything is saved or
        any model is called. The question is answered in a turn: saved first, on its own, so it is kept even if
        answering fails; at most one turn of a conversation runs at a time (TurnInProgress otherwise, with nothing
        saved). With an `idempotency_key`, a repeated request returns the first one's saved answer instead of
        answering again. No database transaction is open while a model is answering.

        Beta: the model writes SQL (or asks, refuses or replies), the guard and the answering rules check it, it runs
        as the read-only role, the model writes the answer from the result and every number in it is checked against
        that result. Each model step gets one second attempt, told what was wrong with the first."""
        question = clean_question(question)
        key = clean_idempotency_key(idempotency_key)
        turn, replay, capped = self._start_turn(user_id, conversation_id, question, mode, key)
        if replay is not None:
            return replay
        try:
            answer = _capped_answer() if capped else self._run_turn(user_id, turn)
        except Exception as exc:
            self._fail_turn(user_id, turn.id, type(exc).__name__)
            raise
        self._record_usage(user_id, turn.id, answer)
        return self._finish_turn(user_id, turn, answer)

    def modes(self, user_id: int | None = None) -> list[ModeStatus]:
        """Which modes are configured on this server (no provider is called to find out). For a user, Standard is
        also unavailable once they reached today's limit or the app reached this month's cap."""
        standard_models = (self._standard.model,) if self._standard is not None else ()
        beta_models = tuple(dict.fromkeys((self._model.sql_model, self._model.answer_model)))
        reason = None if self._standard is not None else "not_configured"
        if reason is None and user_id is not None and self._quota is not None:
            with self._uow(user_id) as work:
                reason = self._limit_reached(work)
        return [
            ModeStatus(AssistantMode.STANDARD, reason is None, standard_models, reason),
            ModeStatus(AssistantMode.BETA, self._beta_available, beta_models,
                       None if self._beta_available else "not_configured"),
        ]  # fmt: skip

    def usage(self, user_id: int) -> UsageView:
        """The user's own question counts (kept when conversations are deleted), and today's Standard questions left."""
        zone = self._quota.time_zone if self._quota else DEFAULT_TIME_ZONE
        with self._uow(user_id) as work:
            today = {mode: work.usage.count_since(mode, "day", zone) for mode in AssistantMode}
            month = {mode: work.usage.count_since(mode, "month", zone) for mode in AssistantMode}
        limit = self._quota.daily_questions_per_user if self._quota else None
        left = None if limit is None else max(limit - today[AssistantMode.STANDARD], 0)
        return UsageView(today, month, limit, left)

    def _limit_reached(self, work: UnitOfWork) -> str | None:
        """Why one more Standard question may not be asked now ("daily_limit" or "monthly_cap"), or None."""
        quota = self._quota
        limit = quota.daily_questions_per_user
        if limit is not None and work.usage.count_since(AssistantMode.STANDARD, "day", quota.time_zone) >= limit:
            return "daily_limit"
        spent, unpriced = work.usage.standard_month_spending(quota.time_zone)
        return "monthly_cap" if over_cap(spent, unpriced, quota) else None

    # --- one turn: start, run, finish ---

    def _start_turn(
        self, user_id: int, conversation_id: int | None, question: str, mode: AssistantMode | None, key: str | None
    ) -> tuple[Turn, AskResult | None, bool]:
        """Save the question, claim the conversation's turn and reserve its usage, or return the earlier answer to a
        repeated request. Raises (with nothing saved) for another user's conversation, a mode conflict, a turn still
        running, or a user past today's Standard limit. The last value says the app's monthly Standard cap is reached:
        the question is then answered "not available" without calling the model.

        A Standard start holds the app-wide start lock until its transaction ends: the limits are checked and the
        question reserved while no other Standard question can start, so two at once cannot both slip under a limit."""
        with self._uow(user_id) as work:  # on its own, so it stays done: give up a turn whose worker stopped
            earlier = work.turns.find_by_key(key) if key is not None else None
            target = earlier.conversation_id if earlier is not None else conversation_id
            if target is not None:
                work.turns.give_up_abandoned(target, self._turn_timeout)

        with self._uow(user_id) as work:
            if key is not None:
                earlier = work.turns.find_by_key(key)
                if earlier is not None:
                    return earlier, self._replay(work, earlier, conversation_id, question, mode), False
            if conversation_id is None:
                chosen = mode or DEFAULT_MODE
                conversation_id = work.conversations.create(title_from(question), chosen)
            else:
                saved_mode = work.conversations.mode_of(conversation_id)
                if saved_mode is None:
                    raise ConversationNotFound
                if mode is not None and mode is not saved_mode:
                    raise AssistantModeConflict
                chosen = saved_mode
            capped = False
            if chosen is AssistantMode.STANDARD and self._standard is not None and self._quota is not None:
                work.usage.lock_standard_starts()
                reason = self._limit_reached(work)
                if reason == "daily_limit":  # raising rolls back the conversation made just now, if any
                    raise DailyLimitReached
                capped = reason == "monthly_cap"
            message = work.messages.add(conversation_id, MessageRole.USER, question)
            turn_id = work.turns.start(conversation_id, message.id, chosen, key)
            if turn_id is None:  # raising rolls back the question (and a conversation made just now)
                raise TurnInProgress
            work.usage.reserve(turn_id, chosen)
        turn = Turn(turn_id, conversation_id, message.id, question, chosen, TurnStatus.RUNNING, idempotency_key=key)
        return turn, None, capped

    def _replay(
        self, work: UnitOfWork, earlier: Turn, conversation_id: int | None, question: str, mode: AssistantMode | None
    ) -> AskResult:
        same = earlier.question == question and conversation_id in (None, earlier.conversation_id)
        if not same or (mode is not None and mode is not earlier.mode):
            raise IdempotencyKeyReused
        if earlier.status is TurnStatus.RUNNING:
            raise TurnInProgress
        if earlier.status is TurnStatus.FAILED or earlier.answer_message_id is None:
            raise IdempotencyKeyReused("That request failed without an answer; ask again with a new Idempotency-Key")
        message = work.messages.get(earlier.answer_message_id)
        if message is None:
            raise ConversationNotFound
        return AskResult(earlier.conversation_id, self._view(work, message), earlier.mode)

    def _run_turn(self, user_id: int, turn: Turn) -> WorkflowAnswer:
        standard = turn.mode is AssistantMode.STANDARD and self._standard is not None
        with self._uow(user_id) as work:
            messages = work.messages.list_for(turn.conversation_id)
            waiting = work.receipts.count_with_status(ReceiptStatus.NEEDS_REVIEW)
            # Standard only: Beta's prompt is its training contract and gets neither memories nor the gender.
            memories = tuple(work.memories.list_all()) if standard else ()
            address = address_for(work.profile.gender()) if standard else None
            # The budget changes the previous answer asked to confirm: the only ones this question may set.
            proposals = budget_proposals(work.turns.previous_execution(turn.conversation_id, turn.id)) if standard \
                else ()  # fmt: skip
        if turn.mode is AssistantMode.BETA:
            history = recent_exchanges(messages, self._history_exchanges, self._history_characters)
            content, details = self._answer(user_id, turn.question, history, waiting)
            models = sorted({attempt.model for attempt in details.attempts})
            execution = {"workflow": "beta", "models": models, "outcome": details.kind.value,
                         "model_calls": len(details.attempts), "duration_ms": details.duration_ms}  # fmt: skip
            # Beta's model reports no tokens: they stay unknown, never 0.
            usage = TurnUsage(len(details.attempts), None, None, None, None, None, None)
            return WorkflowAnswer(content, details, execution, usage)
        if self._standard is None:
            return _not_available("not_configured")
        before = tuple(message for message in messages if message.id != turn.question_message_id)
        request = TurnRequest(user_id, turn.conversation_id, turn.id, turn.question, before, waiting,
                              turn.question_message_id, address, memories, proposals)  # fmt: skip
        return self._standard.answer(request)

    def _finish_turn(self, user_id: int, turn: Turn, answer: WorkflowAnswer) -> AskResult:
        with self._uow(user_id) as work:
            if not work.conversations.hold(turn.conversation_id):  # deleted while answering: never recreated
                raise ConversationNotFound
            message = work.messages.add(turn.conversation_id, MessageRole.ASSISTANT, answer.content, answer.details)
            if not work.turns.complete(turn.id, message.id, answer.execution):
                raise TurnSuperseded  # given up as abandoned meanwhile; this rolls the late answer back
            return AskResult(turn.conversation_id, self._view(work, message), turn.mode)

    def _fail_turn(self, user_id: int, turn_id: int, problem: str) -> None:
        try:
            with self._uow(user_id) as work:
                work.turns.fail(turn_id, problem)
                work.usage.finish(turn_id, f"failed: {problem}", None)  # its cost stays unknown: counted as reserved
        except Exception:  # the original error matters more; the turn is given up later as abandoned
            logger.exception("Could not mark turn %s as failed", turn_id)

    def _record_usage(self, user_id: int, turn_id: int, answer: WorkflowAnswer) -> None:
        """On its own, before the answer is saved: the tokens were spent even if the answer is then not saved (its
        conversation deleted meanwhile, or the turn given up). Best effort: an unrecorded question stays counted at
        the reserve."""
        outcome = (answer.execution or {}).get("outcome") or answer.details.kind.value
        try:
            with self._uow(user_id) as work:
                work.usage.finish(turn_id, str(outcome), answer.usage)
        except Exception:
            logger.exception("Could not record the usage of turn %s", turn_id)

    def run_question(self, user_id: int, question: str, history: Sequence[Exchange] = ()) -> QuestionOutcome:
        """The SQL step on its own: the model turns the question into SQL (or asks, refuses or replies), the guard
        and the answering rules check it, and it runs as the read-only role, with one repair. Nothing is saved.

        `ask` answers with it, and the research evaluation scores it, so both always run exactly the same step.
        Raises ModelUnavailable if no model is configured."""
        question = clean_question(question)
        names = self.prompt_names(user_id)
        attempts: list[Attempt] = []
        outcome = self._write_sql(user_id, question, names, list(history), attempts)
        return QuestionOutcome(
            result=outcome if isinstance(outcome, QueryResult) else None,
            reply=outcome if isinstance(outcome, answers.ModelReply) else None,
            attempts=tuple(attempts),
        )

    def prompt_names(self, user_id: int) -> UserNames:
        """The user's item, vendor and category names exactly as the SQL step's prompt lists them. The research
        dataset builds its training prompts with these, so training matches what the app sends."""
        with self._uow(user_id) as work:
            return UserNames(
                items=names_for_prompt(work.receipts.known_item_names(ITEM_NAMES_LIMIT, MAX_NAME_WORDS),
                                       ITEM_NAMES_LIMIT),
                vendors=work.vendors.recent_names(VENDOR_NAMES_LIMIT),
                categories=[category.name for category in work.categories.list_all()] + list(VIEW_CATEGORIES),
            )  # fmt: skip

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
        # Not given until sign-up asks for it (a later branch); the model then replies without gendered "you" forms.
        prompt = build_prompt(question, names, today, history, gender=Gender.NOT_GIVEN)
        asked = "\n".join([*(exchange.question for exchange in history), question])  # a follow-up keeps its period
        current = prompt
        for _ in range(ATTEMPTS_PER_STEP):
            output = None
            try:
                output = self._model.write_sql(current)
                reply = answers.read_reply(output)
                if reply.form is ReplyForm.SQL:
                    sql = self._rules.prepare(self._guard.check(reply.text), names, today)
                    self._rules.check_dates(sql, asked, today)
                    outcome: QueryResult | answers.ModelReply = self.run_query(user_id, sql)
                    hint = self._size_hint(user_id, sql, outcome)
                    if hint is not None:
                        raise QueryRejected(hint)
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

    def _size_hint(self, user_id: int, sql: str, result: QueryResult) -> str | None:
        """For a price comparison that misses a named shop: how to compare by a size every shop has, or None."""
        query = self._rules.sizes_query(sql)
        if query is None:
            return None
        try:
            sizes = self.run_query(user_id, query)
        except (UnsafeQuery, QueryFailed) as exc:
            logger.warning("The sizes of a comparison could not be found: %s", exc)
            return None
        return self._rules.size_hint(sql, result, sizes)

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
            gender=Gender.NOT_GIVEN,  # as in the SQL step, until sign-up asks
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

    def save_question(
        self, user_id: int, conversation_id: int | None, question: str, mode: AssistantMode = DEFAULT_MODE
    ) -> SavedQuestion:
        """Save a question. Without a conversation id, it starts a new conversation named after it, in `mode`."""
        question = clean_question(question)
        with self._uow(user_id) as work:
            if conversation_id is None:
                conversation_id = work.conversations.create(title_from(question), mode)
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

    def _view(self, work: UnitOfWork, message: Message, still_there: set[int] | None = None) -> MessageView:
        details = message.details
        receipt_ids = details.receipt_ids if details else ()
        if still_there is None:
            still_there = work.receipts.existing_ids(list(receipt_ids))
        understood = None
        if details is not None and details.kind is AnswerKind.ANSWER and details.sql:
            try:
                understood = self._rules.describe(details.sql)
            except QueryRejected:  # saved SQL that no longer parses: no line rather than an error
                understood = None
        return MessageView(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            details=message.details,
            source_receipts=[SourceReceipt(receipt_id, receipt_id in still_there) for receipt_id in receipt_ids],
            rating=message.rating,
            understood=understood,
        )


def _capped_answer() -> WorkflowAnswer:
    """The app reached this month's Standard cap."""
    return _not_available("monthly_cap")


def _not_available(outcome: str) -> WorkflowAnswer:
    """Standard is not available ("monthly_cap", "not_configured"): no model is called, so the question is recorded
    as costing nothing, never as unknown (which would count at the reserve against the monthly cap)."""
    execution = {"workflow": "standard", "outcome": outcome, "calls": [], "tools": []}
    usage = TurnUsage(0, 0, 0, 0, 0, Decimal(0), "no-model-call")
    return WorkflowAnswer(answers.NOT_AVAILABLE, AnswerDetails(AnswerKind.ERROR), execution, usage)
