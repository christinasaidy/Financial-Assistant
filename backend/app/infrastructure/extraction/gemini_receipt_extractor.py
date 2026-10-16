import base64
import json
import logging
import time
from collections.abc import Callable, Sequence

import httpx

from app.domain.receipts.errors import ExtractionFailed
from app.domain.receipts.extraction import ExtractedReceipt
from app.infrastructure.extraction.parsing import parse_extraction

logger = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """You read shop receipts from Lebanon. They may be in Arabic, French or English.
Return the receipt as JSON that follows the schema.

Rules:
- vendor_name: the shop's name as a short display name (e.g. "Spinneys"), not the branch or address.
- receipt_date: the purchase date as YYYY-MM-DD. Lebanese receipts write the day first (DD/MM/YYYY):
  10/05/2026 is 10 May 2026, not 5 October.
- currency: "USD" or "LBP". Use the currency the total is printed in.
- total: the final amount paid, as a plain number.
- lines: one entry per purchased product. Do not include tax, discount, subtotal or payment lines.
  - description: the text exactly as printed on the receipt, in its original language.
  - normalized_name: what the product IS, as a generic English name of 1 to 3 lowercase words, always the
    same for the same product. Never include the brand, the size or count, small/large, the fat level or the
    flavour: "PRESIDENT FULL CREAM MILK 2L" -> "milk", "Strawberry Crepe" -> "crepe", "Large Water" -> "water",
    "Green Tea" -> "tea". Keep the product type, not the broad family: "penne", not "pasta"; "latte", not
    "coffee". Translate Arabic and French names into English: "خبز عربي" -> "bread", "FROMAGE RAPE" -> "cheese".
    Lebanese foods with no English word use exactly these spellings: "manakish" (whatever the topping),
    "labneh", "laban", "zaatar", "halloumi", "kaak".
    If the product is the same as one of the user's existing item names listed below, return that name
    exactly as listed. Leave it null if the line is unclear.
  - brand: the maker's brand as printed, in lowercase Latin letters (transliterate Arabic), e.g. "barilla",
    "almarai". A shop's own brand counts. Null when no brand is printed; never guess one. Ingredients are not
    brands: "Nutella Waffle" has no brand.
  - size_amount and size_unit: the size of ONE unit when it is printed (e.g. 250 and "ml", 1 and "l",
    2 and "kg", 6 and "pcs"). Leave both null when no size is printed. Never guess a size.
  - quantity: how many units were bought (1 if not shown).
  - unit_price: price of one unit if printed, otherwise null.
  - line_total: the amount charged for the line.
  - category: the best match from this list, or null if none fits: {categories}.
- Use null for anything you cannot read. Never invent values.

The user's existing item names, most recently used first: {known_names}"""

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
                    "brand": _NULLABLE_STRING,
                },
                "required": ["description", "line_total"],
            },
        },
    },
    "required": ["lines"],
}


# Google answers 429 (rate limit) and 5xx (often "high demand") for a while and then recovers, so these are
# worth waiting for. Anything else (a wrong request, a retired model) will not get better by trying again.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
DEFAULT_WAITS = (2.0, 5.0)  # seconds before the 2nd and 3rd attempt with the same model


class _Retryable(Exception):
    """A temporary failure: worth waiting and trying the same model again."""


class GeminiReceiptExtractor:
    """Reads a receipt with Gemini. Each model is tried up to three times when Google is overloaded or slow,
    waiting a little longer each time; if it still fails, the next model in `models` is tried."""

    def __init__(
        self,
        api_key: str,
        models: str | Sequence[str],
        client: httpx.Client | None = None,
        waits: Sequence[float] = DEFAULT_WAITS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._models = [models] if isinstance(models, str) else [model for model in models if model]
        self._client = client or httpx.Client(timeout=60)
        self._waits = tuple(waits)
        self._sleep = sleep

    def extract(
        self, content: bytes, content_type: str, category_names: Sequence[str], known_names: Sequence[str] = ()
    ) -> ExtractedReceipt:
        prompt = PROMPT.format(
            categories=", ".join(category_names) or "(none)",
            known_names=", ".join(f'"{name}"' for name in known_names) or "(none yet)",
        )
        body = {
            "contents": [
                {
                    "parts": [
                        {"inline_data": {"mime_type": content_type, "data": base64.b64encode(content).decode()}},
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
            },
        }
        failures: list[str] = []
        for model in self._models:
            for attempt, wait in enumerate((0.0, *self._waits), start=1):
                if wait:
                    self._sleep(wait)
                try:
                    data = self._ask(model, body)
                except _Retryable as exc:
                    failures.append(f"{model} attempt {attempt}: {exc}")
                    logger.warning("Gemini %s attempt %s failed, will retry: %s", model, attempt, exc)
                    continue
                except ExtractionFailed as exc:
                    failures.append(f"{model}: {exc}")
                    logger.warning("Gemini %s failed, trying the next model if any: %s", model, exc)
                    break  # retrying the same model will not help
                # Only a usable answer gets here. If it does not match the schema, another model would
                # not be more trustworthy, so parse_extraction's ExtractionFailed is raised as is.
                return parse_extraction(data)
        raise ExtractionFailed("Gemini could not read the receipt: " + " | ".join(failures)[:1500])

    def _ask(self, model: str, body: dict) -> object:
        try:
            response = self._client.post(
                API_URL.format(model=model), headers={"x-goog-api-key": self._api_key}, json=body
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise _Retryable(type(exc).__name__) from exc
        except httpx.HTTPError as exc:
            raise ExtractionFailed(f"The vision model did not return a usable answer ({type(exc).__name__})") from exc
        if response.status_code >= 400:
            # The body says why (overloaded, quota, retired model). It never contains the API key.
            message = f"HTTP {response.status_code}: {response.text[:500]}"
            if response.status_code in RETRYABLE_STATUS:
                raise _Retryable(message)
            raise ExtractionFailed(f"Gemini returned {message}")
        try:
            answer = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            # parse_float=str keeps money exact: the text goes straight to Decimal, never through float.
            return json.loads(answer, parse_float=str)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ExtractionFailed(f"The vision model did not return a usable answer ({type(exc).__name__})") from exc
