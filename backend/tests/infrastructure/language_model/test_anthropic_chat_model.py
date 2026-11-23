"""The Anthropic adapter through the real SDK, against a fake HTTP transport (no network, no paid call): what is sent
(instructions, tools, cache points, effort, tool results paired with their calls, thinking blocks sent back
unchanged), what is read back (text, tool calls, stop reason, usage, request id) and how failures end (AC-06, AC-18,
AC-19). The responses are written by the tests in the documented shape, so they prove the protocol only."""

import json

import anthropic
import httpx2
import pytest

from app.application.assistant.dtos import ChatMessage, ChatRequest, TextPart, ToolCall, ToolResult, ToolSpec
from app.domain.assistant.errors import ModelFailed
from app.infrastructure.language_model.anthropic_chat_model import AnthropicChatModel

KEY = "sk-ant-test-not-a-real-key"
SCHEMA = {"type": "object", "properties": {"year": {"type": "integer"}}, "required": ["year"],
          "additionalProperties": False}  # fmt: skip
TOOL = ToolSpec("get_budgets", "Budgets for a month", SCHEMA)


def _message(content, stop_reason="end_turn", usage=None):
    body = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
            "content": content, "stop_reason": stop_reason, "stop_sequence": None,
            "usage": usage or {"input_tokens": 1200, "output_tokens": 40, "cache_creation_input_tokens": 900,
                               "cache_read_input_tokens": 0}}  # fmt: skip
    return httpx2.Response(200, json=body, headers={"request-id": "req_abc"})


class Server:
    """Answers each request with the next scripted response and keeps every request body."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.bodies: list[dict] = []
        self.headers: list = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.bodies.append(json.loads(request.content))
        self.headers.append(request.headers)
        step = self.responses.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def _model(server, **options):
    client = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(server))
    options = {"max_retries": 0} | options
    return AnthropicChatModel(KEY, "claude-sonnet-5-5", http_client=client, **options)


def _ask(*messages, allow_tools=True):
    return ChatRequest("You are the assistant.", (TOOL,), tuple(messages) or (ChatMessage("user", (TextPart("hi"),)),),
                       allow_tools)  # fmt: skip


def test_the_request_has_the_instructions_tools_cache_points_and_effort():
    server = Server(_message([{"type": "text", "text": "Hello!"}]))
    _model(server, max_output_tokens=2048, effort="medium").respond(_ask())
    body = server.bodies[0]
    assert body["model"] == "claude-sonnet-5-5"
    assert body["max_tokens"] == 2048
    cached = {"type": "ephemeral"}
    assert body["system"] == [{"type": "text", "text": "You are the assistant.", "cache_control": cached}]
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["tools"] == [{"name": "get_budgets", "description": "Budgets for a month", "strict": True,
                              "input_schema": TOOL.input_schema}]  # fmt: skip
    assert body["output_config"] == {"effort": "medium"}
    assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
    for refused in ("temperature", "top_p", "top_k", "thinking", "tool_choice"):  # refused by this model, or default
        assert refused not in body
    # The key goes in its header only (SDK 2.x sends it as a bearer token), with the SDK's API version.
    assert server.headers[0]["authorization"] == f"Bearer {KEY}"
    assert server.headers[0]["anthropic-version"] == "2026-10-21"
    assert KEY not in json.dumps(body)


def test_after_the_limits_tools_are_switched_off_with_tool_choice_none():
    server = Server(_message([{"type": "text", "text": "Done."}]))
    _model(server).respond(_ask(allow_tools=False))
    assert server.bodies[0]["tool_choice"] == {"type": "none"}
    assert server.bodies[0]["tools"]  # still defined: earlier messages contain tool calls


def test_text_tool_calls_usage_and_request_id_are_read_back():
    server = Server(_message([
        {"type": "thinking", "thinking": "", "signature": "sig-1"},
        {"type": "text", "text": "Let me check."},
        {"type": "tool_use", "id": "toolu_9", "name": "get_budgets", "input": {"year": 2026}},
    ], stop_reason="tool_use"))  # fmt: skip
    response = _model(server).respond(_ask())
    assert response.parts == (TextPart("Let me check."), ToolCall("toolu_9", "get_budgets", {"year": 2026}))
    assert response.stop_reason == "tool_use"
    assert response.model == "claude-sonnet-5-5"
    assert response.request_id == "req_abc"
    usage = response.usage
    assert (usage.input_tokens, usage.output_tokens, usage.cache_creation_input_tokens,
            usage.cache_read_input_tokens) == (1200, 40, 900, 0)  # fmt: skip


def test_a_reply_goes_back_unchanged_with_its_thinking_and_results_follow_their_calls():
    first = [{"type": "thinking", "thinking": "", "signature": "sig-1"},
             {"type": "tool_use", "id": "toolu_9", "name": "get_budgets", "input": {"year": 2026}}]  # fmt: skip
    server = Server(_message(first, stop_reason="tool_use"), _message([{"type": "text", "text": "No budgets."}]))
    model = _model(server)
    question = ChatMessage("user", (TextPart("budgets?"),))
    reply = model.respond(_ask(question))
    results = ChatMessage("user", (ToolResult("toolu_9", '{"budgets": []}', False), TextPart("answer now")))
    model.respond(_ask(question, ChatMessage("assistant", reply.parts, reply.provider_content), results))

    sent = server.bodies[1]["messages"]
    assert sent[1]["role"] == "assistant"
    assert sent[1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig-1"}
    assert sent[1]["content"][1]["id"] == "toolu_9"
    assert sent[2] == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_9", "content": '{"budgets": []}', "is_error": False},
        {"type": "text", "text": "answer now"},
    ]}  # fmt: skip


def test_saved_history_without_provider_content_is_rebuilt_from_its_parts():
    server = Server(_message([{"type": "text", "text": "ok"}]))
    _model(server).respond(_ask(ChatMessage("user", (TextPart("q1"),)), ChatMessage("assistant", (TextPart("a1"),)),
                                ChatMessage("user", (TextPart("q2"),))))  # fmt: skip
    assert server.bodies[0]["messages"][1] == {"role": "assistant", "content": [{"type": "text", "text": "a1"}]}


def test_missing_usage_counts_are_unknown_not_zero():
    server = Server(_message([{"type": "text", "text": "Hi"}], usage={"input_tokens": 10, "output_tokens": 2}))
    usage = _model(server).respond(_ask()).usage
    assert (usage.cache_creation_input_tokens, usage.cache_read_input_tokens) == (None, None)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (httpx2.Response(500, json={"type": "error", "error": {"type": "api_error", "message": "boom " + KEY}}),
         "The Standard model returned an error (HTTP 500)"),
        (httpx2.Response(429, json={"type": "error", "error": {"type": "rate_limit_error", "message": "slow"}}),
         "The Standard model returned an error (HTTP 429)"),
        (httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "key"}}),
         "The Standard model returned an error (HTTP 401)"),
        (httpx2.ReadTimeout("timed out"), "The Standard model did not answer in time"),
        (httpx2.ConnectError("refused"), "The Standard model could not be reached"),
        (httpx2.Response(200, content=b"<html>not json</html>", headers={"content-type": "application/json"}),
         "The Standard model's response could not be used"),
    ],
)  # fmt: skip
def test_failures_become_a_short_model_failed_without_the_key(failure, message):
    with pytest.raises(ModelFailed) as raised:
        _model(Server(failure)).respond(_ask())
    assert str(raised.value).startswith(message)
    assert KEY not in str(raised.value) and "boom" not in str(raised.value)


def test_retries_are_bounded_by_max_retries():
    error = httpx2.Response(503, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}},
                            headers={"retry-after-ms": "1"})  # fmt: skip
    server = Server(error, error, error)
    with pytest.raises(ModelFailed):
        _model(server, max_retries=1).respond(_ask())
    assert len(server.bodies) == 2  # the first try and one retry, never more
    assert len(server.responses) == 1


def test_one_client_serves_every_request_and_closes():
    server = Server(_message([{"type": "text", "text": "a"}]), _message([{"type": "text", "text": "b"}]))
    model = _model(server)
    client = model._client
    assert [model.respond(_ask()).text, model.respond(_ask()).text] == ["a", "b"]
    assert model._client is client
    model.close()


def test_an_unknown_effort_is_refused_at_startup():
    with pytest.raises(ValueError):
        AnthropicChatModel(KEY, "claude-sonnet-5-5", effort="extreme")
