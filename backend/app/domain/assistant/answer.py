"""Reading the model's replies and checking its answers (assistant phase 3, approved by the user on 2026-11-03).

- The SQL step replies with one SELECT, `CLARIFY: <question>`, `UNSUPPORTED` or `REPLY: <text>`. Code fences and
  surrounding spaces are removed first; anything else cannot be used and the model is asked once more.
- The answer step writes the answer from the query's result. Every number in it must come from that result (a
  cell, a date in it, or the total of a column), from the number of source receipts, from today's date, or from
  the question or the SQL that ran ("per 100 g", "top 3"). A clarifying question or a short reply may only repeat
  numbers from the question, since the model saw no data for it.
- Only numbers standing on their own are checked. Digits inside a word are Arabizi letters ("sha3er", "ma7al"),
  not numbers. Numbers written as words ("three", "tleteh") are not checked (a known limitation).
- A few messages are fixed, in English only, because they must work when the model does not.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.domain.assistant.errors import UnusableReply

NO_MATCHES = "I couldn't find any confirmed receipts matching that."
UNSUPPORTED = (
    "I can answer questions about your confirmed receipts: what you spent, on what, where and when, "
    "and what you paid for items. For budgets, see the Budgets screen."
)
FAILURE = "Sorry, I couldn't answer that. Try asking it a different way."
NOT_AVAILABLE = "The assistant isn't available right now."
TABLE_INTRO = "Here are the results:"


def review_note(waiting: int) -> str:
    """Added to an answer while some receipts have not been confirmed yet (they are not counted)."""
    if waiting == 1:
        return "1 receipt is still waiting for your review and isn't included."
    return f"{waiting} receipts are still waiting for your review and aren't included."


class ReplyForm(StrEnum):
    SQL = "sql"
    CLARIFY = "clarify"
    UNSUPPORTED = "unsupported"
    REPLY = "reply"


@dataclass(frozen=True)
class ModelReply:
    form: ReplyForm
    text: str  # the SQL, or the text to show the user ("" for UNSUPPORTED)


_FENCE = re.compile(r"^```[A-Za-z]*\s*(.*?)\s*```$", re.DOTALL)
_FORMS_MESSAGE = "Reply with one SELECT query, CLARIFY: <question>, UNSUPPORTED or REPLY: <text>, and nothing else"


def read_reply(raw: str | None) -> ModelReply:
    """What the SQL step replied, or UnusableReply if it is none of the four forms."""
    text = (raw or "").strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    upper = text.upper()
    for prefix, form in (("CLARIFY:", ReplyForm.CLARIFY), ("REPLY:", ReplyForm.REPLY)):
        if upper.startswith(prefix):
            message = text[len(prefix) :].strip()
            if not message:
                raise UnusableReply(f"{prefix} must be followed by the text to show")
            return ModelReply(form, message)
    if upper.rstrip(".") == "UNSUPPORTED":
        return ModelReply(ReplyForm.UNSUPPORTED, "")
    first_word = upper.split(maxsplit=1)[0] if upper else ""
    if first_word in ("SELECT", "WITH"):
        return ModelReply(ReplyForm.SQL, text)
    raise UnusableReply(_FORMS_MESSAGE)


# A number standing on its own: not touching a letter or digit, and not part of a bigger number. "1,450,000",
# "16.20" and "$3.75" are numbers; the 3 in "3al" and in "dafa3et" is a letter.
_NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?!\w)")


def numbers_in(text: str) -> list[Decimal]:
    """The standalone numbers written in a text, as exact values (signs are ignored)."""
    return [Decimal(whole.replace(",", "") + (f".{fraction}" if fraction else "")) for whole, fraction in
            _NUMBER.findall(text)]  # fmt: skip


def result_numbers(rows: Sequence[Sequence[object]]) -> list[Decimal]:
    """Every number in a query result: numeric cells, the day, month and year of dates, and numbers inside text."""
    found: list[Decimal] = []
    for row in rows:
        for value in row:
            found.extend(_numbers_of(value))
    return found


def column_totals(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> dict[str, Decimal]:
    """The total of each numeric column over two or more rows, exactly (rounded only when shown)."""
    totals: dict[str, Decimal] = {}
    if len(rows) < 2:
        return totals
    for index, name in enumerate(columns):
        values = [row[index] for row in rows if index < len(row)]
        numbers = [_as_decimal(value) for value in values if _as_decimal(value) is not None]
        if numbers:
            totals[name] = sum(numbers, Decimal(0))
    return totals


def date_numbers(day: date) -> list[Decimal]:
    return [Decimal(day.day), Decimal(day.month), Decimal(day.year)]


def check_numbers(text: str, allowed: Sequence[Decimal], source: str) -> None:
    """Raise UnusableReply if the text states a number that is not one of `allowed`.

    A written number matches an allowed value if it equals it, or equals it rounded to the places written:
    "$29.70" matches 29.7011, "1000 g" matches 1000.000, "about $16" matches 16.20."""
    allowed_values = [abs(value) for value in allowed]
    wrong = [number for number in numbers_in(text) if not any(_matches(number, value) for value in allowed_values)]
    if wrong:
        listed = ", ".join(_plain(number) for number in wrong)
        raise UnusableReply(f"It states numbers that are not in {source}: {listed}")


def is_empty_result(rows: Sequence[Sequence[object]]) -> bool:
    """No rows, or only empty values (SUM over nothing is NULL): nothing matched."""
    return all(value is None for row in rows for value in row)


def as_text(rows: Sequence[Sequence[object]]) -> tuple[tuple[str | None, ...], ...]:
    """A result as text, for a table answer saved with the message (amounts stay exact)."""
    return tuple(tuple(_cell_text(value) for value in row) for row in rows)


def _numbers_of(value: object) -> list[Decimal]:
    if isinstance(value, datetime):
        return date_numbers(value.date())
    if isinstance(value, date):
        return date_numbers(value)
    number = _as_decimal(value)
    if number is not None:
        return [number]
    if isinstance(value, str):
        return numbers_in(value)
    return []


def _as_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    return None


def _matches(written: Decimal, value: Decimal) -> bool:
    if written == value:
        return True
    places = max(0, -written.as_tuple().exponent)
    try:
        return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP) == written
    except ArithmeticError:  # more places than a Decimal can hold: it cannot be a rounding of the value
        return False


def _plain(number: Decimal) -> str:
    return format(number, "f")


def _cell_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)
