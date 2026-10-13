import base64
import json
from collections.abc import Sequence

import httpx

from app.domain.receipts.errors import ExtractionFailed
from app.domain.receipts.extraction import ExtractedReceipt
from app.infrastructure.extraction.parsing import parse_extraction

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """You read shop receipts from Lebanon. They may be in Arabic, French or English.
Return the receipt as JSON that follows the schema.

Rules:
- vendor_name: the shop's name as a short display name (e.g. "Spinneys"), not the branch or address.
- receipt_date: the purchase date as YYYY-MM-DD.
- currency: "USD" or "LBP". Use the currency the total is printed in.
- total: the final amount paid, as a plain number.
- lines: one entry per purchased product. Do not include tax, discount, subtotal or payment lines.
  - description: the text exactly as printed on the receipt, in its original language.
  - normalized_name: a short lowercase product name in Latin letters (e.g. "laban", "olive oil").
    Leave it null if the line is unclear.
  - size_amount and size_unit: the size of ONE unit when it is printed (e.g. 250 and "ml", 1 and "l",
    2 and "kg", 6 and "pcs"). Leave both null when no size is printed. Never guess a size.
  - quantity: how many units were bought (1 if not shown).
  - unit_price: price of one unit if printed, otherwise null.
  - line_total: the amount charged for the line.
  - category: the best match from this list, or null if none fits: {categories}.
- Use null for anything you cannot read. Never invent values."""

_NULLABLE_STRING = {"type": "STRING", "nullable": True}
_NULLABLE_NUMBER = {"type": "NUMBER", "nullable": True}
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "vendor_name": _NULLABLE_STRING,
        "receipt_date": _NULLABLE_STRING,
        "currency": {"type": "STRING", "enum": ["USD", "LBP"], "nullable": True},
        "total": _NULLABLE_NUMBER,
        "lines": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "description": {"type": "STRING"},
                    "normalized_name": _NULLABLE_STRING,
                    "size_amount": _NULLABLE_NUMBER,
                    "size_unit": _NULLABLE_STRING,
                    "quantity": {"type": "NUMBER"},
                    "unit_price": _NULLABLE_NUMBER,
                    "line_total": {"type": "NUMBER"},
                    "category": _NULLABLE_STRING,
                },
                "required": ["description", "line_total"],
            },
        },
    },
    "required": ["lines"],
}


class GeminiReceiptExtractor:
    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._url = API_URL.format(model=model)
        self._client = client or httpx.Client(timeout=60)

    def extract(self, content: bytes, content_type: str, category_names: Sequence[str]) -> ExtractedReceipt:
        body = {
            "contents": [
                {
                    "parts": [
                        {"inline_data": {"mime_type": content_type, "data": base64.b64encode(content).decode()}},
                        {"text": PROMPT.format(categories=", ".join(category_names) or "(none)")},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
            },
        }
        try:
            response = self._client.post(self._url, headers={"x-goog-api-key": self._api_key}, json=body)
            response.raise_for_status()
            answer = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            # parse_float=str keeps money exact: the text goes straight to Decimal, never through float.
            data = json.loads(answer, parse_float=str)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ExtractionFailed("The vision model did not return a usable answer") from exc
        return parse_extraction(data)
