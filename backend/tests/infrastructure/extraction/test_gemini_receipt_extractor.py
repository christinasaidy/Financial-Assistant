"""The Gemini adapter against a fake HTTP server. No real API call is made here."""

import base64
import json
from decimal import Decimal

import httpx
import pytest

from app.domain.receipts.errors import ExtractionFailed
from app.infrastructure.extraction.gemini_receipt_extractor import GeminiReceiptExtractor


def extractor_answering(handler) -> GeminiReceiptExtractor:
    return GeminiReceiptExtractor("test-key", "test-model", client=httpx.Client(transport=httpx.MockTransport(handler)))


def gemini_reply(text: str) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def test_sends_the_file_and_parses_the_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-goog-api-key"]
        seen["body"] = json.loads(request.content)
        return gemini_reply(
            '{"vendor_name": "Spinneys", "total": 2.10, "lines": [{"description": "laban", "line_total": 2.10}]}'
        )

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
