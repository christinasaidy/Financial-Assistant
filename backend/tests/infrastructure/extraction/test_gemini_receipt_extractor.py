"""The Gemini adapter against a fake HTTP server. No real API call is made here."""

import base64
import json
from decimal import Decimal

import httpx
import pytest

from app.domain.receipts.errors import ExtractionFailed
from app.infrastructure.extraction.gemini_receipt_extractor import GeminiReceiptExtractor


def extractor_answering(handler, models="test-model", waits=None) -> GeminiReceiptExtractor:
    """An extractor talking to a fake server. Waiting between retries is recorded, not slept."""
    extractor = GeminiReceiptExtractor(
        "test-key",
        models,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=(waits.append if waits is not None else lambda seconds: None),
    )
    return extractor


def gemini_reply(text: str) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def test_sends_the_file_and_parses_the_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-goog-api-key"]
        seen["body"] = json.loads(request.content)
        return gemini_reply('{"vendor_name": "Spinneys", "total": 2.10, "lines": [{"description": "laban", "line_total": 2.10}]}')

    receipt = extractor_answering(handler).extract(b"image-bytes", "image/jpeg", ["Groceries", "Dining"])

    assert receipt.vendor_name == "Spinneys"
    assert receipt.total == Decimal("2.10")  # exact, not 2.1000000000000000888
    assert receipt.lines[0].line_total == Decimal("2.10")

    assert seen["url"].endswith("/models/test-model:generateContent")
    assert seen["key"] == "test-key"
    file_part, text_part = seen["body"]["contents"][0]["parts"]
    assert file_part["inline_data"] == {"mime_type": "image/jpeg", "data": base64.b64encode(b"image-bytes").decode()}
    assert "Groceries, Dining" in text_part["text"]
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="server error"),
        httpx.Response(429, text="rate limited"),
        httpx.Response(200, json={"candidates": []}),
        httpx.Response(200, json={"unexpected": "shape"}),
        gemini_reply("this is not json"),
        gemini_reply('{"lines": [{"description": "x"}]}'),  # breaks the schema
    ],
)
def test_bad_answers_become_extraction_failed(response):
    with pytest.raises(ExtractionFailed):
        extractor_answering(lambda request: response).extract(b"x", "image/png", [])


def test_network_errors_become_extraction_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network")

    with pytest.raises(ExtractionFailed):
        extractor_answering(handler).extract(b"x", "image/png", [])


def test_an_http_error_says_what_the_api_answered():
    reply = httpx.Response(404, text='{"error": {"message": "model not found"}}')
    with pytest.raises(ExtractionFailed, match="HTTP 404.*model not found"):
        extractor_answering(lambda request: reply).extract(b"x", "image/png", [])


# --- Retrying when Google is overloaded (seen on 2026-10-15: many 503 "high demand" replies) ---

GOOD = '{"vendor_name": "Spinneys", "total": 9.37, "lines": [{"description": "milk", "line_total": 9.37}]}'
HIGH_DEMAND = httpx.Response(503, json={"error": {"message": "This model is currently experiencing high demand."}})


def replies(*responses):
    """A fake server that answers with these responses in order, and records which model was asked."""
    queue, asked = list(responses), []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path.split("/models/")[1].split(":")[0])
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return handler, asked


def test_an_overloaded_model_is_retried_after_waiting():
    handler, asked = replies(HIGH_DEMAND, HIGH_DEMAND, gemini_reply(GOOD))
    waits: list[float] = []
    receipt = extractor_answering(handler, waits=waits).extract(b"x", "image/png", [])
    assert receipt.vendor_name == "Spinneys"
    assert asked == ["test-model"] * 3
    assert waits == [2.0, 5.0]  # waits longer each time


@pytest.mark.parametrize(
    "temporary",
    [
        httpx.Response(429, text="rate limited"),
        httpx.Response(500, text="internal"),
        httpx.Response(504, text="gateway timeout"),
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("no network"),
    ],
)
def test_other_temporary_failures_are_retried_too(temporary):
    handler, asked = replies(temporary, gemini_reply(GOOD))
    assert extractor_answering(handler).extract(b"x", "image/png", []).total == Decimal("9.37")
    assert len(asked) == 2


def test_after_three_overloads_it_gives_up_and_says_why():
    handler, asked = replies(HIGH_DEMAND, HIGH_DEMAND, HIGH_DEMAND)
    with pytest.raises(ExtractionFailed, match="high demand"):
        extractor_answering(handler).extract(b"x", "image/png", [])
    assert len(asked) == 3


def test_the_fallback_model_is_used_when_the_first_stays_overloaded():
    handler, asked = replies(HIGH_DEMAND, HIGH_DEMAND, HIGH_DEMAND, gemini_reply(GOOD))
    receipt = extractor_answering(handler, models=["first", "second"]).extract(b"x", "image/png", [])
    assert receipt.vendor_name == "Spinneys"
    assert asked == ["first", "first", "first", "second"]


def test_a_retired_model_is_not_retried_but_the_fallback_is_tried():
    retired = httpx.Response(404, json={"error": {"message": "no longer available to new users"}})
    handler, asked = replies(retired, gemini_reply(GOOD))
    receipt = extractor_answering(handler, models=["old", "new"]).extract(b"x", "image/png", [])
    assert receipt.vendor_name == "Spinneys"
    assert asked == ["old", "new"]


def test_an_answer_that_breaks_the_schema_is_not_retried():
    handler, asked = replies(gemini_reply('{"lines": [{"description": "x"}]}'), gemini_reply(GOOD))
    with pytest.raises(ExtractionFailed):
        extractor_answering(handler, models=["first", "second"]).extract(b"x", "image/png", [])
    assert asked == ["first"]


def test_an_empty_fallback_setting_is_ignored():
    handler, asked = replies(gemini_reply(GOOD))
    extractor_answering(handler, models=["only", None, ""]).extract(b"x", "image/png", [])
    assert asked == ["only"]
