"""Whether the model's reply to a test question is correct (rules approved by the user on 2026-11-05).

A question expecting a query is right when the model's query returns the same result as the expected one, run on
the same data on the same day:
- the same number of rows;
- every column of the expected result matches one of the model's columns, value for value in the same rows (extra
  model columns are ignored, and so are column names);
- row order is ignored, unless the expected query has ORDER BY and LIMIT ("latest", "top 3");
- amounts are compared to the cent; dates and text exactly (a timestamp at midnight, with or without a time
  zone, counts as its date: date_trunc('month', ...) is the same month as a date);
- no rows, a row of only NULLs and a row of only zeros all mean "nothing matched", and count as the same answer.
A question expecting CLARIFY, UNSUPPORTED or REPLY is right when the model replied with that form (its wording is
not scored). Some questions accept more than one answer. Right "on the first try" means no repair was needed.
"""

import itertools
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal

import sqlglot
from sqlglot import exp

from app.application.assistant.dtos import QueryResult, QuestionOutcome
from app.domain.assistant.answer import ReplyForm
from research.evaluation.questions import PilotQuestion

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Score:
    correct: bool
    first_try: bool
    reason: str  # why it is wrong ("" when right)


def score(question: PilotQuestion, outcome: QuestionOutcome, expected: Sequence[QueryResult | None]) -> Score:
    """`expected` holds the result of each accepted query (None for an accepted reply type), in the same order."""
    for accepted, result in zip(question.accept, expected):
        if accepted.reply is not None and outcome.reply is not None and outcome.reply.form is accepted.reply:
            return _right(outcome)
        if accepted.sql is not None and outcome.result is not None and result is not None:
            if results_match(result, outcome.result, is_ordered(accepted.sql)):
                return _right(outcome)
    return Score(False, False, _why_wrong(question, outcome))


def results_match(expected: QueryResult, actual: QueryResult, ordered: bool = False) -> bool:
    want = [tuple(_normal(value) for value in row) for row in expected.rows]
    got = [tuple(_normal(value) for value in row) for row in actual.rows]
    if _nothing(want) or _nothing(got):
        return _nothing(want) and _nothing(got)
    if len(want) != len(got):
        return False
    columns = len(want[0]) if want else 0
    candidates = []
    for index in range(columns):
        column = [row[index] for row in want]
        matching = [j for j in range(len(got[0])) if _same([row[j] for row in got], column, ordered)]
        if not matching:
            return False
        candidates.append(matching)
    for choice in itertools.product(*candidates):  # which model column stands for each expected column
        if len(set(choice)) != len(choice):
            continue
        picked = [tuple(row[j] for j in choice) for row in got]
        if (picked == want) if ordered else (Counter(picked) == Counter(want)):
            return True
    return False


def is_ordered(sql: str) -> bool:
    """Does the expected query pick rows by their order (ORDER BY with LIMIT)? Then the order is part of the answer."""
    tree = sqlglot.parse_one(sql, read="postgres")
    return isinstance(tree, exp.Select) and bool(tree.args.get("order")) and bool(tree.args.get("limit"))


def _right(outcome: QuestionOutcome) -> Score:
    first_try = bool(outcome.attempts) and outcome.attempts[0].problem is None
    return Score(True, first_try, "")


def _why_wrong(question: PilotQuestion, outcome: QuestionOutcome) -> str:
    wants_sql = any(accepted.sql for accepted in question.accept)
    wants = {accepted.reply.value.upper() for accepted in question.accept if accepted.reply}
    if outcome.result is None and outcome.reply is None:
        last = outcome.attempts[-1].problem if outcome.attempts else "no attempt"
        return f"failed: {last}"
    if outcome.reply is not None:
        got = outcome.reply.form.value.upper()
        if wants_sql and outcome.reply.form is ReplyForm.CLARIFY:
            return "asked a clarifying question instead of answering"
        return f"replied {got}, expected " + (" or ".join(sorted(wants)) or "a query")
    if not wants_sql:
        return "guessed with a query, expected " + " or ".join(sorted(wants))
    return "wrong result"


def _same(values: list, column: list, ordered: bool) -> bool:
    return values == column if ordered else Counter(values) == Counter(column)


def _nothing(rows: list[tuple]) -> bool:
    return all(value is None or (isinstance(value, Decimal) and value == 0) for row in rows for value in row)


def _normal(value: object) -> object:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    if isinstance(value, datetime):
        return value.date() if value.time() == time(0) else value  # date_trunc gives midnight in local time
    if isinstance(value, date):
        return value
    return str(value)
