"""The Standard workflow's loop with a scripted model and stub tools (no database, no provider): tool calls paired
with their results, the limits, the number check, failures and the execution record (AC-06, AC-14, AC-15, AC-17,
AC-19). The model's replies are set by each test, so these prove the protocol, never what a real model would say."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from app.application.assistant.dtos import ChatResponse, ModelUsage, TextPart, ToolCall, ToolResult, TurnRequest
from app.application.assistant.standard_prompt import PROMPT_VERSION, SYSTEM_PROMPT
from app.application.assistant.standard_tools import SPECS, TOOLS_VERSION, ToolOutcome
from app.application.assistant.standard_workflow import StandardLimits, StandardWorkflow
from app.domain.assistant import answer as answers
from app.domain.assistant.conversation import AnswerKind, Message, MessageRole
from app.domain.assistant.errors import ModelFailed
from tests.fakes import ScriptedChatModel, calls, says

TODAY = date(2026, 11, 23)  # a Monday
SUM_SQL = {"sql": "SELECT SUM(total) AS spent FROM receipts"}


class StubTools:
    specs = SPECS

    def __init__(self, outcome: ToolOutcome | None = None) -> None:
        self.outcome = outcome or ToolOutcome('{"rows": [["42.50"]]}', False, (Decimal("42.50"),), (7, 9), True,
                                              {"name": "query_receipts", "ok": True})  # fmt: skip
        self.calls: list[tuple[int, ToolCall]] = []

    def run(self, user_id, call, context):
        self.calls.append((user_id, call))
        assert context.today == TODAY
        return self.outcome


def _request(question="How much did I spend?", history=(), waiting=0, user_id=11) -> TurnRequest:
    return TurnRequest(user_id, 5, 3, question, tuple(history), waiting)


def _workflow(model, tools=None, limits=StandardLimits(), clock=None):
    ticks = iter(range(10_000))
    return StandardWorkflow(model, tools or StubTools(), lambda: TODAY, limits, clock or (lambda: next(ticks) * 0.001))


def _message(role, content, i=1):
    return Message(i, MessageRole(role), content, datetime(2026, 11, 1, tzinfo=UTC))


def test_a_greeting_is_one_call_and_no_tool():
    model = ScriptedChatModel(says("Hi! Ask me about your receipts."))
    tools = StubTools()
    answer = _workflow(model, tools).answer(_request("hi"))
    assert answer.content == "Hi! Ask me about your receipts."
    assert answer.details.kind is AnswerKind.REPLY
    assert len(model.requests) == 1 and tools.calls == []
    sent = model.requests[0]
    assert sent.system == SYSTEM_PROMPT and sent.tools == SPECS and sent.allow_tools
    # today's date goes with the question, never into the cached instructions
    assert "2026-11-23" not in sent.system
    context = ("[Context for this question] Today is Monday 2026-11-23 (Beirut). No receipts are waiting for review. "
               "Arabizi reply forms, only if you reply in Arabizi: the neutral forms (gender not given).\n"
               "[Saved memories] none")  # fmt: skip
    assert sent.messages[-1].parts == (TextPart(context), TextPart("hi"))
    assert answer.execution["outcome"] == "answered" and answer.execution["tools"] == []
    assert answer.execution["prompt_version"] == PROMPT_VERSION
    assert answer.execution["tools_version"] == TOOLS_VERSION


def test_a_tool_result_is_paired_with_its_call_and_the_answer_cites_its_receipts():
    model = ScriptedChatModel(calls(("toolu_1", "query_receipts", SUM_SQL)), says("You spent $42.50."))
    tools = StubTools()
    answer = _workflow(model, tools).answer(_request(user_id=11))

    assert [user for user, _ in tools.calls] == [11]  # the signed-in user, never one from the model
    second = model.requests[1].messages
    assistant, results = second[-2], second[-1]
    assert assistant.role == "assistant" and assistant.provider_content == ("provider", (("toolu_1", "query_receipts",
                                                                                          SUM_SQL),))  # fmt: skip
    assert results.role == "user"
    assert results.parts == (ToolResult("toolu_1", '{"rows": [["42.50"]]}', False),)
    assert answer.content == "You spent $42.50."
    assert answer.details.kind is AnswerKind.ANSWER
    assert answer.details.receipt_ids == (7, 9)
    assert answer.execution["sources_complete"] is True
    assert [call["stop_reason"] for call in answer.execution["calls"]] == ["tool_use", "end_turn"]


def test_every_call_of_a_reply_gets_its_own_result_in_order():
    model = ScriptedChatModel(calls(("a", "get_budgets", {}), ("b", "find_names", {})), says("Done."))
    _workflow(model).answer(_request())
    results = model.requests[1].messages[-1].parts
    assert [r.call_id for r in results] == ["a", "b"]


def test_tool_calls_past_the_limit_are_not_run_and_the_model_must_then_answer():
    many = [(f"t{i}", "query_receipts", SUM_SQL) for i in range(10)]
    model = ScriptedChatModel(calls(*many), says("You spent $42.50."))
    tools = StubTools()
    answer = _workflow(model, tools, StandardLimits(max_tool_calls=8)).answer(_request())
    assert len(tools.calls) == 8
    results = model.requests[1].messages[-1].parts
    assert [r.call_id for r in results[:10]] == [f"t{i}" for i in range(10)]  # all paired, results first
    assert [r.is_error for r in results[:10]] == [False] * 8 + [True] * 2
    assert isinstance(results[-1], TextPart) and "last tool use" in results[-1].text
    assert model.requests[1].allow_tools is False
    assert answer.details.kind is AnswerKind.ANSWER


def test_after_the_last_tool_round_the_model_answers_without_tools():
    round_ = calls(("t", "query_receipts", SUM_SQL))
    model = ScriptedChatModel(round_, round_, says("You spent $42.50."))
    answer = _workflow(model, limits=StandardLimits(max_tool_rounds=2)).answer(_request())
    assert [request.allow_tools for request in model.requests] == [True, True, False]
    assert answer.details.kind is AnswerKind.ANSWER


def test_asking_for_tools_after_the_limit_fails_the_answer():
    round_ = calls(("t", "query_receipts", SUM_SQL))
    model = ScriptedChatModel(round_, round_)
    answer = _workflow(model, limits=StandardLimits(max_tool_rounds=1)).answer(_request())
    assert (answer.details.kind, answer.content) == (AnswerKind.ERROR, answers.FAILURE)
    assert answer.execution["outcome"] == "tools_after_limit"


def test_a_number_not_in_the_evidence_is_sent_back_once_with_the_problem():
    model = ScriptedChatModel(calls(("t", "query_receipts", SUM_SQL)), says("You spent $85.00, twice $42.50."),
                              says("You spent $42.50."))  # fmt: skip
    answer = _workflow(model).answer(_request())
    assert answer.content == "You spent $42.50."
    fix = model.requests[2].messages[-1].parts[0].text
    assert "85" in fix and "query_receipts" in fix
    first, second = answer.details.attempts
    assert first.problem and "85" in first.problem and second.problem is None


def test_a_price_per_100_g_is_a_unit_not_a_figure_but_other_numbers_are_still_checked():
    """Found in the live test of 2026-11-23: "per 100 g" (the price_comparisons skill's wording) was refused."""
    laban = ToolOutcome('{"rows": [["Carrefour", "0.30"]]}', False, (Decimal("0.30"),), (4,), True, {})
    model = ScriptedChatModel(calls(("t", "query_receipts", SUM_SQL)), says("Carrefour: $0.30 per 100 g (100ml too)."))
    assert _workflow(model, StubTools(laban)).answer(_request()).content == "Carrefour: $0.30 per 100 g (100ml too)."
    model = ScriptedChatModel(calls(("t", "query_receipts", SUM_SQL)), says("Carrefour: $100 per 100 g."),
                              says("Carrefour: $0.30 per 100 g."))  # fmt: skip
    assert _workflow(model, StubTools(laban)).answer(_request()).content == "Carrefour: $0.30 per 100 g."


def test_an_answer_that_fails_the_number_check_twice_is_not_shown():
    model = ScriptedChatModel(says("You spent $85.00."), says("Still $85.00."))
    answer = _workflow(model).answer(_request())
    assert (answer.details.kind, answer.content) == (AnswerKind.ERROR, answers.FAILURE)
    assert answer.execution["outcome"] == "unchecked_answer"


def test_numbers_from_the_question_the_date_and_earlier_answers_are_allowed():
    history = [_message("user", "and in October?", 1), _message("assistant", "You spent $12.00 in October.", 2)]
    model = ScriptedChatModel(says("In October you spent $12.00; today is the 23rd, and you asked about 3 shops."))
    answer = _workflow(model).answer(_request("compare 3 shops", history))
    assert answer.details.kind is AnswerKind.REPLY


def test_a_cut_off_answer_is_an_error_not_a_partial_answer():
    model = ScriptedChatModel(ChatResponse((TextPart("You spent"),), "max_tokens", "fake-sonnet"))
    answer = _workflow(model).answer(_request())
    assert (answer.details.kind, answer.content) == (AnswerKind.ERROR, answers.FAILURE)
    assert answer.execution["outcome"] == "stopped_max_tokens"
    assert answer.details.attempts[0].problem == "Stopped: max_tokens"


def test_a_refusal_is_saved_as_unsupported():
    model = ScriptedChatModel(ChatResponse((), "refusal", "fake-sonnet"))
    answer = _workflow(model).answer(_request())
    assert (answer.details.kind, answer.content) == (AnswerKind.UNSUPPORTED, answers.UNSUPPORTED)


def test_a_model_failure_is_an_error_answer_and_never_another_mode():
    model = ScriptedChatModel(ModelFailed("The Standard model did not answer in time"))
    answer = _workflow(model).answer(_request())
    assert (answer.details.kind, answer.content) == (AnswerKind.ERROR, answers.FAILURE)
    assert answer.details.attempts[0].problem == "The Standard model did not answer in time"
    assert answer.execution["outcome"] == "model_failed"
    assert answer.execution["usage"]["input_tokens"] is None  # the failed call reported nothing: unknown


def test_an_empty_answer_is_retried_once():
    model = ScriptedChatModel(says(""), says("Hello!"))
    assert _workflow(model).answer(_request("hi")).content == "Hello!"


def test_no_new_call_starts_after_the_deadline():
    times = iter([0.0, 0.0, 1.0, 1.0, 500.0, 500.0, 500.0])
    model = ScriptedChatModel(calls(("t", "query_receipts", SUM_SQL)), says("unused"))
    answer = _workflow(model, clock=lambda: next(times)).answer(_request())
    assert len(model.requests) == 1
    assert answer.execution["outcome"] == "deadline"


def test_usage_is_summed_and_unknown_when_any_call_did_not_report_it():
    model = ScriptedChatModel(calls(("t", "query_receipts", SUM_SQL), usage=ModelUsage(100, 20, 80, 0)),
                              says("You spent $42.50.", usage=ModelUsage(150, 10, 0, 90)))  # fmt: skip
    usage = _workflow(model).answer(_request()).execution["usage"]
    assert usage == {"input_tokens": 250, "output_tokens": 30, "cache_creation_input_tokens": 80,
                     "cache_read_input_tokens": 90}  # fmt: skip

    model = ScriptedChatModel(calls(("t", "query_receipts", SUM_SQL)), says("You spent $42.50.", usage=None))
    usage = _workflow(model).answer(_request()).execution["usage"]
    assert usage["output_tokens"] is None  # not reported is not zero


def test_the_history_is_the_newest_messages_starting_with_a_question():
    history = [_message("user", "q1", 1), _message("assistant", "a1", 2), _message("user", "q2", 3),
               _message("assistant", "a2", 4)]  # fmt: skip
    model = ScriptedChatModel(says("ok"))
    _workflow(model, limits=StandardLimits(history_messages=3)).answer(_request("q3", history))
    sent = model.requests[0].messages
    assert [(m.role, m.parts[0].text) for m in sent[:-1]] == [("user", "q2"), ("assistant", "a2")]
    assert sent[-1].parts[-1] == TextPart("q3")


def test_receipts_waiting_for_review_are_noted_under_answers_from_data_only():
    model = ScriptedChatModel(calls(("t", "query_receipts", SUM_SQL)), says("You spent $42.50."))
    answer = _workflow(model).answer(_request(waiting=2))
    assert answer.content == f"You spent $42.50. {answers.review_note(2)}"
    assert "2 receipts are waiting" in model.requests[0].messages[-1].parts[0].text

    model = ScriptedChatModel(says("Hi!"))
    assert _workflow(model).answer(_request("hi", waiting=2)).content == "Hi!"


def test_a_failed_tool_is_not_evidence_and_does_not_make_sources_complete():
    failed = ToolOutcome(json.dumps({"error": "The tool failed"}), True, (), (), False, {"ok": False})
    model = ScriptedChatModel(calls(("t", "query_receipts", SUM_SQL)), says("I couldn't check that, sorry."))
    answer = _workflow(model, StubTools(failed)).answer(_request())
    assert model.requests[1].messages[-1].parts[0].is_error is True
    assert answer.details.kind is AnswerKind.REPLY  # no data was looked at
    assert answer.details.receipt_ids == ()
    assert answer.execution["sources_complete"] is None


def test_sources_are_incomplete_when_a_data_result_cannot_list_its_receipts():
    summary = ToolOutcome('{"combined": {"total": "42.50"}}', False, ({"total": "42.50"},), (), False, {})
    model = ScriptedChatModel(calls(("t", "get_spending_summary", {})), says("You spent $42.50."))
    answer = _workflow(model, StubTools(summary)).answer(_request())
    assert answer.details.kind is AnswerKind.ANSWER
    assert answer.execution["sources_complete"] is False


def test_each_answer_carries_its_estimated_cost_with_the_pricing_version():
    from app.domain.assistant.usage import Pricing

    prices = Pricing("test-prices", Decimal("2"), Decimal("10"), Decimal("2.5"), Decimal("4"), Decimal("0.1"))
    ticks = iter(range(10_000))
    model = ScriptedChatModel(calls(("t", "query_receipts", SUM_SQL), usage=ModelUsage(100, 20, 0, 0)),
                              says("You spent $42.50.", usage=ModelUsage(50, 10, 0, 0)))  # fmt: skip
    workflow = StandardWorkflow(model, StubTools(), lambda: TODAY, clock=lambda: next(ticks) * 0.001, pricing=prices)
    answer = workflow.answer(_request())
    assert (answer.usage.model_calls, answer.usage.input_tokens, answer.usage.output_tokens) == (2, 150, 30)
    assert answer.usage.dollars == Decimal("0.000600")  # (150 * 2 + 30 * 10) per million
    assert answer.execution["cost"] == {"dollars": "0.000600", "pricing_version": "test-prices"}

    failed = StandardWorkflow(ScriptedChatModel(ModelFailed("timeout")), StubTools(), lambda: TODAY, pricing=prices)
    assert failed.answer(_request()).usage.dollars is None  # a failed call may have cost something: unknown
