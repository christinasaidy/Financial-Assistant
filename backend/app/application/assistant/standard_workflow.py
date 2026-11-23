"""The Standard mode's workflow: the hosted model answers with the app's read-only tools (2026-11-23).

One question is answered in a bounded loop:
1. the model gets its fixed instructions, the tools, the recent conversation and the question (with today's date);
2. if it asks for tools, they run (as the signed-in user) and their results go back to it, each paired with its call;
3. it either answers or asks for more tools, up to the limits below; then it must answer without tools;
4. every number in the answer is checked against the tool results, the question and the earlier answers (one retry,
   told what was wrong), and the answer is returned with an execution record of what happened.

The model decides whether a question needs a tool: a greeting is normally one call and no tool; a spending question
normally a tool and a second call. Nothing classifies the question beforehand.

Bounds: tool rounds, tool calls, and the whole question's time (the adapter bounds each call and its retries).
The model's failures, refusals and cut-off answers become an error answer saved like any other; nothing here
falls back to the Beta workflow.
"""

import json
import logging
import re
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.application.assistant.dtos import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    TextPart,
    ToolResult,
    TurnRequest,
    WorkflowAnswer,
)
from app.application.assistant.interfaces import StandardChatModel
from app.application.assistant.standard_prompt import PROMPT_VERSION, SYSTEM_PROMPT, turn_context
from app.application.assistant.standard_skills import Skill, instructions
from app.application.assistant.standard_tools import (
    TOOLS_VERSION,
    StandardTools,
    ToolContext,
    ToolOutcome,
    memory_line,
)
from app.domain.assistant import answer as answers
from app.domain.assistant import arabizi
from app.domain.assistant.arabizi import ArabiziWords
from app.domain.assistant.conversation import AnswerDetails, AnswerKind, Attempt, Message, MessageRole, Step
from app.domain.assistant.errors import ModelFailed, UnusableReply
from app.domain.assistant.prompt import WEEKDAYS
from app.domain.assistant.usage import CallTokens, Pricing, turn_usage

logger = logging.getLogger(__name__)

FINISHED = frozenset({"end_turn", "stop_sequence"})
# The unit a price comparison is given per (the price_comparisons skill): "100 g", "100ml", "100 grams".
_UNIT_SIZE = re.compile(r"(?<![\d.,])100\s?(g|gr|grams?|ml)\b", re.IGNORECASE)
# An answer saying a memory was saved, changed or forgotten (English only: Arabizi wording is not guessed here).
_MEMORY_CLAIM = re.compile(
    r"\b(i'?ve|i have|i)\s+(saved|stored|remembered|noted|forgotten|deleted|updated)\b|\bi'?ll\s+(remember|forget)\b"
    r"|\bi will\s+(remember|forget)\b|^\s*(saved|done, saved|noted)\b|\bsaved\s+(it|that|this)\b",
    re.IGNORECASE,
)
_NO_MORE_TOOLS = (
    "That was the last tool use allowed for this question. Answer now with what the results above show, and say "
    "what you could not check."
)


@dataclass(frozen=True)
class StandardLimits:
    max_tool_rounds: int = 4  # model replies that ask for tools; then one more call must answer without them
    max_tool_calls: int = 8  # tools run per question; calls past it are answered "limit reached", not run
    deadline_seconds: float = 240.0  # no new model call starts after this (each call is bounded by the adapter)
    number_repairs: int = 1  # retries of an answer whose numbers are not in the evidence
    history_messages: int = 12  # the conversation sent with the question: the newest messages,
    history_characters: int = 8_000  # dropping the oldest first


class StandardWorkflow:
    """Implements StandardAssistant. Built once per process (the model client, the tools and the instructions are
    reused); every request's state lives in `answer`'s locals."""

    def __init__(
        self,
        model: StandardChatModel,
        tools: StandardTools,
        today: Callable[[], date],
        limits: StandardLimits = StandardLimits(),
        clock: Callable[[], float] = time.monotonic,
        *,
        skills: Sequence[Skill] = (),
        arabizi_words: ArabiziWords | None = None,
        pricing: Pricing | None = None,
    ) -> None:
        """`skills` are added to the fixed instructions once, here; `arabizi_words` (from the owner's pack) are what
        every answer is checked against."""
        self.model = model.model
        self._chat = model
        self._tools = tools
        self._today = today
        self._limits = limits
        self._clock = clock
        self._system = instructions(SYSTEM_PROMPT, skills) if skills else SYSTEM_PROMPT
        self._skills = {skill.name: skill.version for skill in skills}
        self._arabizi = arabizi_words
        self._pricing = pricing  # None: no cost estimate (unknown, not 0)

    def answer(self, request: TurnRequest) -> WorkflowAnswer:
        run = _Run(self._clock(), self._today())
        context = ToolContext(run.today, "\n".join([*_questions(request.history), request.question]),
                              request.conversation_id, request.question_message_id)  # fmt: skip
        opening = turn_context(run.today.isoformat(), WEEKDAYS[run.today.weekday()], request.receipts_waiting,
                               request.address.value, tuple(memory_line(m) for m in request.memories))  # fmt: skip
        own_words = [request.question, *(m.content for m in request.history), *(m.text for m in request.memories)]
        messages = [*_history(request.history, self._limits), ChatMessage("user", (TextPart(opening),
                                                                                    TextPart(request.question)))]
        allowed = [*answers.numbers_in(request.question), *answers.date_numbers(run.today),
                   *(n for m in request.history for n in answers.numbers_in(m.content))]  # fmt: skip
        allow_tools, rounds, repairs = True, 0, 0

        while True:
            if self._clock() - run.started > self._limits.deadline_seconds:
                return self._failed(run, "deadline", "The question took too long to answer")
            started = self._clock()
            try:
                response = self._chat.respond(ChatRequest(self._system, self._tools.specs, tuple(messages),
                                                          allow_tools))  # fmt: skip
            except ModelFailed as exc:
                run.calls.append({"duration_ms": _ms(self._clock() - started), "problem": str(exc)})
                run.attempts.append(Attempt(Step.ANSWER, self.model, None, str(exc)))
                return self._failed(run, "model_failed", str(exc))
            run.record_call(response, self._clock() - started)

            if response.stop_reason == "tool_use" and response.tool_calls:
                if not allow_tools:
                    return self._failed(run, "tools_after_limit", "The model asked for tools after the last round")
                rounds += 1
                results = [self._run_tool(request.user_id, call, context, run) for call in response.tool_calls]
                parts: tuple = tuple(results)
                if rounds >= self._limits.max_tool_rounds or run.tool_calls >= self._limits.max_tool_calls:
                    allow_tools = False
                    parts += (TextPart(_NO_MORE_TOOLS),)  # text after every result, as the protocol requires
                messages += [ChatMessage("assistant", response.parts, response.provider_content),
                             ChatMessage("user", parts)]  # fmt: skip
                continue

            if response.stop_reason == "refusal":
                return self._finish(run, AnswerKind.UNSUPPORTED, answers.UNSUPPORTED, "refused", request)
            if response.stop_reason not in FINISHED:  # max_tokens, model_context_window_exceeded, pause_turn, ...
                run.attempts.append(Attempt(Step.ANSWER, response.model, response.text or None,
                                            f"Stopped: {response.stop_reason}"))  # fmt: skip
                return self._failed(run, f"stopped_{response.stop_reason}", "The answer was not finished")
            text = response.text
            found = self._check(text, run, allowed, own_words, request)
            if found:
                problem = "; ".join(found)
                run.attempts.append(Attempt(Step.ANSWER, response.model, text or None, problem))
                run.checks.append(problem)
                if repairs >= self._limits.number_repairs:
                    return self._failed(run, "unchecked_answer", problem)
                repairs += 1
                fix = f"Your answer was not shown: {problem}. Answer again without these problems."
                messages += [ChatMessage("assistant", response.parts, response.provider_content),
                             ChatMessage("user", (TextPart(fix),))]  # fmt: skip
                continue
            run.attempts.append(Attempt(Step.ANSWER, response.model, text))
            kind = AnswerKind.ANSWER if run.used_data else AnswerKind.REPLY
            return self._finish(run, kind, text, "answered", request)

    def _check(
        self, text: str, run: "_Run", allowed: list[Decimal], own_words: list[str], request: TurnRequest
    ) -> list[str]:
        """What is wrong with an answer before it may be shown; empty when nothing is."""
        if not text:
            return ["the answer is empty"]
        found = []
        try:
            figures = _UNIT_SIZE.sub("", text)  # "per 100 g" is how a comparison is put, not a figure from the data
            answers.check_numbers(figures, [*allowed, *run.evidence_numbers()], "the tool results")
        except UnusableReply as exc:
            found.append(f"{exc} (use only numbers from the tool results; have query_receipts compute any)")
        if self._arabizi is not None:
            spelling = arabizi.problems(text, self._arabizi, request.address, [*own_words, *run.contents])
            if spelling:
                logger.warning("Standard answer broke the Arabizi rulings: %s", "; ".join(spelling))
                found += [f"{problem} (follow the lebanese_arabizi skill)" for problem in spelling]
        if _MEMORY_CLAIM.search(text) and not run.memory_written:
            found.append("it says a memory was saved, changed or forgotten, but no memory tool succeeded")
        return found

    def _run_tool(self, user_id: int, call, context: ToolContext, run: "_Run") -> ToolResult:
        if run.tool_calls >= self._limits.max_tool_calls:
            run.tools.append({"name": call.name, "ok": False, "problem": "tool call limit reached (not run)"})
            content = json.dumps({"error": "The limit of tool calls for this question is reached; this was not run"})
            return ToolResult(call.id, content, is_error=True)
        run.tool_calls += 1
        outcome = self._tools.run(user_id, call, context)
        run.add(outcome)
        return ToolResult(call.id, outcome.content, outcome.is_error)

    def _finish(self, run: "_Run", kind: AnswerKind, text: str, outcome: str, request: TurnRequest) -> WorkflowAnswer:
        if kind is AnswerKind.ANSWER and request.receipts_waiting:  # as Beta: unconfirmed receipts are not counted
            text = f"{text} {answers.review_note(request.receipts_waiting)}"
        return self._answer(run, kind, text, outcome)

    def _failed(self, run: "_Run", outcome: str, problem: str) -> WorkflowAnswer:
        return self._answer(run, AnswerKind.ERROR, answers.FAILURE, outcome, problem)

    def _answer(
        self, run: "_Run", kind: AnswerKind, text: str, outcome: str, problem: str | None = None
    ) -> WorkflowAnswer:
        duration_ms = _ms(self._clock() - run.started)
        usage = turn_usage([_call_tokens(call) for call in run.calls], self._pricing)
        details = AnswerDetails(kind, receipt_ids=run.receipt_ids(), duration_ms=duration_ms,
                                attempts=tuple(run.attempts))  # fmt: skip
        execution = {
            "workflow": "standard",
            "prompt_version": PROMPT_VERSION,
            "tools_version": TOOLS_VERSION,
            "skills": self._skills,  # name -> version, e.g. the Arabizi pack's fingerprint
            "checks": run.checks,  # problems found in answers that were sent back (never shown)
            "configured_model": self.model,
            "models": sorted({call["model"] for call in run.calls if call.get("model")}),
            "outcome": outcome,
            "problem": problem,
            "today": run.today.isoformat(),
            "limits": {"max_tool_rounds": self._limits.max_tool_rounds, "max_tool_calls": self._limits.max_tool_calls,
                       "deadline_seconds": self._limits.deadline_seconds},  # fmt: skip
            "calls": run.calls,
            "tools": run.tools,
            "usage": _total_usage(run.calls),
            "cost": {"dollars": None if usage.dollars is None else str(usage.dollars),
                     "pricing_version": usage.pricing_version},
            "sources_complete": run.sources_complete(),
            "duration_ms": duration_ms,
        }
        return WorkflowAnswer(text, details, execution, usage)


class _Run:
    """What one question's loop has done so far."""

    def __init__(self, started: float, today: date) -> None:
        self.started = started
        self.today = today
        self.calls: list[dict] = []
        self.tools: list[dict] = []
        self.attempts: list[Attempt] = []
        self.checks: list[str] = []
        self.tool_calls = 0
        self._outcomes: list[ToolOutcome] = []

    @property
    def contents(self) -> list[str]:
        """Every successful tool result's text: names in it are the data's, never held against an answer."""
        return [o.content for o in self._outcomes if not o.is_error]

    @property
    def memory_written(self) -> bool:
        return any(o.memory_written and not o.is_error for o in self._outcomes)

    def record_call(self, response: ChatResponse, seconds: float) -> None:
        usage = response.usage
        self.calls.append({
            "model": response.model,
            "request_id": response.request_id,
            "stop_reason": response.stop_reason,
            "duration_ms": _ms(seconds),
            "tool_calls": len(response.tool_calls),
            "usage": None if usage is None else {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_creation_input_tokens": usage.cache_creation_input_tokens,
                "cache_read_input_tokens": usage.cache_read_input_tokens,
                "cache_write_5m_tokens": usage.cache_write_5m_tokens,
                "cache_write_1h_tokens": usage.cache_write_1h_tokens,
            },
        })  # fmt: skip

    def add(self, outcome: ToolOutcome) -> None:
        self._outcomes.append(outcome)
        self.tools.append(outcome.record)

    @property
    def used_data(self) -> bool:
        return any(not o.is_error and o.sources_listed is not None for o in self._outcomes)

    def evidence_numbers(self) -> list[Decimal]:
        return [n for o in self._outcomes if not o.is_error for value in o.evidence for n in _numbers(value)]

    def receipt_ids(self) -> tuple[int, ...]:
        return tuple(dict.fromkeys(i for o in self._outcomes if not o.is_error for i in o.receipt_ids))

    def sources_complete(self) -> bool | None:
        """Whether every data result's receipts are listed. None when no data was looked at."""
        data = [o for o in self._outcomes if not o.is_error and o.sources_listed is not None]
        return None if not data else all(o.sources_listed for o in data)


def _history(history: Iterable[Message], limits: StandardLimits) -> list[ChatMessage]:
    """The newest saved messages that fit, as plain text (only what the user saw: tool results are not kept between
    questions, so no result can be left without its call). It starts with a question, as the provider requires."""
    kept: list[Message] = []
    size = 0
    for message in reversed(list(history)):
        size += len(message.content)
        if len(kept) >= limits.history_messages or size > limits.history_characters:
            break
        kept.append(message)
    kept.reverse()
    while kept and kept[0].role is not MessageRole.USER:
        kept.pop(0)
    return [ChatMessage(message.role.value, (TextPart(message.content),)) for message in kept]


def _questions(history: Iterable[Message]) -> list[str]:
    return [message.content for message in history if message.role is MessageRole.USER]


def _numbers(value: object) -> list[Decimal]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, Decimal)):
        return [Decimal(value)]
    if isinstance(value, str):
        return answers.numbers_in(value)
    if isinstance(value, dict):
        return [n for item in value.values() for n in _numbers(item)]
    if isinstance(value, (list, tuple)):
        return [n for item in value for n in _numbers(item)]
    return answers.numbers_in(str(value))


def _total_usage(calls: list[dict]) -> dict:
    """Each token count summed over the calls, or None when any call did not report it (unknown, not zero)."""
    fields = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    totals: dict = {}
    for name in fields:
        values = [(call.get("usage") or {}).get(name) for call in calls]
        totals[name] = None if not values or any(v is None for v in values) else sum(values)
    return totals


def _call_tokens(call: dict) -> CallTokens | None:
    """A call's reported tokens; None for a call that reported nothing (it failed, or gave no usage)."""
    usage = call.get("usage")
    if usage is None:
        return None
    return CallTokens(usage["input_tokens"], usage["output_tokens"], usage["cache_creation_input_tokens"],
                      usage.get("cache_write_5m_tokens"), usage.get("cache_write_1h_tokens"),
                      usage["cache_read_input_tokens"])  # fmt: skip


def _ms(seconds: float) -> int:
    return round(seconds * 1000)
