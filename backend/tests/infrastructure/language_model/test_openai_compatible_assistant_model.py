"""The language-model client against a fake HTTP server. No real API call is made here."""

import json

import httpx
import pytest

from app.domain.assistant.errors import ModelFailed, ModelUnavailable
from app.infrastructure.language_model.openai_compatible_assistant_model import OpenAiCompatibleAssistantModel
from app.infrastructure.language_model.unavailable_assistant_model import UnavailableAssistantModel


def model_answering(handler, waits=None) -> OpenAiCompatibleAssistantModel:
    return OpenAiCompatibleAssistantModel(
        "https://example.test/v1beta/openai/",
        "test-key",
        "sql-adapter",
        "base-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=(waits.append if waits is not None else lambda seconds: None),
    )


def chat_reply(text) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": text}}]})


def test_sends_the_prompt_to_the_chat_api_and_returns_the_text():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers["authorization"], json.loads(request.content)))
        return chat_reply("SELECT 1")

    model = model_answering(handler)
    assert model.write_sql("the prompt") == "SELECT 1"
    assert model.write_answer("another prompt") == "SELECT 1"

    (url, auth, body), (_, _, answer_body) = seen
    assert url == "https://example.test/v1beta/openai/chat/completions"
    assert auth == "Bearer test-key"
    assert body == {"model": "sql-adapter", "messages": [{"role": "user", "content": "the prompt"}], "temperature": 0}
    assert answer_body["model"] == "base-model"  # the answer step: the same base model, adapter off
    assert (model.sql_model, model.answer_model) == ("sql-adapter", "base-model")


@pytest.mark.parametrize("first", [httpx.Response(429, text="rate limited"), httpx.Response(503, text="overloaded")])
def test_a_temporary_failure_is_tried_once_more_after_two_seconds(first):
    responses = [first, chat_reply("SELECT 1")]
    waits: list[float] = []
    assert model_answering(lambda request: responses.pop(0), waits).write_sql("p") == "SELECT 1"
    assert waits == [2.0]


def test_a_timeout_is_tried_once_more():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return chat_reply("SELECT 1")

    assert model_answering(handler).write_sql("p") == "SELECT 1"
    assert len(calls) == 2


def test_two_temporary_failures_give_up():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, text="overloaded")

    with pytest.raises(ModelFailed, match="503"):
        model_answering(handler).write_sql("p")
    assert len(calls) == 2


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, text="bad request"),
        httpx.Response(401, text="bad key"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"unexpected": "shape"}),
        httpx.Response(200, text="not json"),
        chat_reply(None),
    ],
)
def test_anything_else_fails_at_once(response):
    calls = []

    def handler(request):
        calls.append(1)
        return response

    with pytest.raises(ModelFailed) as failed:
        model_answering(handler).write_sql("p")
    assert len(calls) == 1
    assert "test-key" not in str(failed.value)


def test_without_a_key_the_assistant_is_unavailable():
    with pytest.raises(ModelUnavailable):
        UnavailableAssistantModel().write_sql("p")
    with pytest.raises(ModelUnavailable):
        UnavailableAssistantModel().write_answer("p")


@pytest.mark.parametrize(("thinking", "sent"), [(None, None), (False, {"enable_thinking": False}),
                                                (True, {"enable_thinking": True})])  # fmt: skip
def test_thinking_is_sent_only_when_set(thinking, sent):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return chat_reply("SELECT 1")

    model = OpenAiCompatibleAssistantModel("https://example.test/v1", "k", "m", "m", thinking=thinking,
                                           client=httpx.Client(transport=httpx.MockTransport(handler)))  # fmt: skip
    model.write_sql("p")
    assert bodies[0].get("chat_template_kwargs") == sent  # None: nothing sent, so Gemini is never confused by it


@pytest.mark.parametrize(("value", "expected"), [("", None), ("  ", None), ("false", False), ("true", True)])
def test_the_thinking_setting_treats_empty_as_unset(value, expected, monkeypatch):
    from app.infrastructure.config import Settings

    monkeypatch.setenv("ASSISTANT_THINKING", value)
    assert Settings().assistant_thinking is expected
