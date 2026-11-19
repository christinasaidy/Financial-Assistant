"""Earlier exchanges put in front of stored questions, so training looks like a real chat (batch 5 part 1).

Decided with Christina on 2026-11-17/18 (agent_documentation/PROGRESS.md):
- History replaces lines, never adds copies: a question that gets history is the same example with earlier
  exchanges in front, and its own gold reply is unchanged.
- Earlier exchanges are other questions of the same user and split, with their own gold replies. Arabizi and mixed
  ones come only from lines she reviewed (batches 3 and 4); English ones from any batch. About 70% are SQL turns and
  about 80% are in the question's language group (English, or Arabizi and mixed).
- Per question, history on at most a third of its versions, and at least one Arabizi version keeps none.
- Among the examples with history about 70% ignore it (a new question that states what it needs; a refusal; thanks;
  "ma fhemet") and about 30% use it (follow-ups). The share is checked: 65-75%.
- 1-6 earlier exchanges, 35 / 25 / 17 / 11 / 7 / 5%, under the app's own limits: the history goes through the app's
  `recent_exchanges` (6 exchanges, 6,000 characters), so it is exactly what the app would send.
- English follow-ups (their earlier question is already in front) get older exchanges in front of about a third.
- Plain chats (Christina, 2026-11-19: long chats where nothing goes wrong were missing): half of the chats with 3 or
  more earlier exchanges in front of a normal question are only normal questions and answers.

The builder's own rules, so that no two chats teach opposite things (the approved prompt line: what a new question
leaves out comes from the earlier question):
- A new SQL question with no period never follows a question with one, unless its kind takes no period (the last
  time, how often, since when, a price change, the cheapest brand); with no item, shop, category or brand, it never
  follows a question that has one. "The question it follows" is the nearest earlier one with these (thanks, a
  refusal or "what can you do" have none).
- Questions whose reply would change once something is earlier in the chat never get history: vague ones that
  refer to "it" or "there" (C3), "hal fatra" and "bi awal el shaher" (C4), greetings (R1).
- Earlier exchanges never include follow-ups, sign-offs (R5), vague questions (C3, C4) or "ma fhemet" (C6); a
  greeting comes only first, thanks only right after an answer.
"""

import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.assistant.conversation import AnswerDetails, AnswerKind, Message, MessageRole
from app.domain.assistant.prompt import Exchange, build_prompt, recent_exchanges

from research.dataset.rerender import read_prompt
from research.dataset.users import gender_of

MAX_EXCHANGES = 6  # the app's DEFAULT_HISTORY_EXCHANGES
MAX_CHARACTERS = 6000  # the app's DEFAULT_HISTORY_CHARACTERS
LENGTHS = ((1, 0.35), (2, 0.25), (3, 0.17), (4, 0.11), (5, 0.07), (6, 0.05))
INDEPENDENT_SHARE = 0.70
INDEPENDENT_RANGE = (0.65, 0.75)
SQL_SHARE = 0.70
SAME_LANGUAGE = 0.80
FOLLOW_UPS_WITH_OLDER = 1 / 3
PLAIN_FROM = 3  # earlier exchanges
PLAIN_SHARE = 0.5
SEED = "fyp-dataset/history-batch5"
TRIES = 40

NO_PERIOD_KINDS = {"T11", "T11k", "B4", "B6", "B11", "B13", "B15"}
NEVER_GIVEN = {"C3", "R1"}  # plus C4 for "hal fatra" and "bi awal el shaher"
NEVER_EARLIER = {"C3", "C4", "C6", "R5"}
VAGUE_PERIODS = {"hal fatra", "bi awal el shaher"}
_WHAT = re.compile(r"\b(item_name|vendor|category|brand)\s*(=|IN)\s*(\([^)]*\)|'(?:[^']|'')*')", re.IGNORECASE)


class HistoryError(ValueError):
    """The history cannot be built as approved (the share of examples that ignore it is out of range)."""


@dataclass(frozen=True)
class Turn:
    """An example that can be shown as an earlier exchange or be given history."""

    index: int
    question: str
    reply: str
    template: str
    kind: str
    group: str  # "english" or "arabizi" (Arabizi and mixed)
    spec: str
    reviewed: bool
    period: bool | None  # None: says nothing about a period (thanks, refusals)
    what: frozenset | None  # None: says nothing about an item, shop or category

    @property
    def is_sql(self) -> bool:
        return self.kind == "sql"


def _turn(index: int, row: dict) -> Turn:
    labels = row["labels"]
    reply = row["messages"][1]["content"]
    template, kind = labels["template"], labels["kind"]
    if kind == "sql":
        period = labels.get("period", "none") != "none"
        what = frozenset((m.group(1).lower(), m.group(3)) for m in _WHAT.finditer(reply))
    elif template in ("C1", "C2", "C5", "C7", "C8"):  # an item or shop the user does not have, a lost receipt
        period, what = False, frozenset({("asked", template)})
    else:
        period, what = None, None
    spec = labels["spec"]
    return Turn(index, read_prompt(row["messages"][0]["content"]).question, reply, template, kind,
                "english" if labels["language"] == "english" else "arabizi", spec,
                labels["language"] == "english" or spec.startswith(("b3-", "b4-")), period, what)  # fmt: skip


def can_be_earlier(turn: Turn) -> bool:
    return turn.reviewed and turn.kind != "follow_up" and turn.template not in NEVER_EARLIER


def can_be_given(turn: Turn, row: dict) -> bool:
    if not turn.reviewed or turn.kind == "follow_up" or turn.template in NEVER_GIVEN:
        return False
    return not (turn.template == "C4" and str(row["labels"].get("period")) in VAGUE_PERIODS)


def well_ordered(earlier: list[Turn]) -> bool:
    """Distinct questions; a greeting only first; thanks only right after an answer."""
    if len({turn.spec for turn in earlier}) != len(earlier):
        return False
    for position, turn in enumerate(earlier):
        if turn.template == "R1" and position != 0:
            return False
        if turn.template == "R2" and (position == 0 or not earlier[position - 1].is_sql):
            return False
    return True


def follows_well(question: Turn, earlier: list[Turn]) -> bool:
    """Whether `question` can come right after `earlier` (oldest first) without contradicting the prompt line."""
    if any(turn.spec == question.spec for turn in earlier) or not well_ordered(earlier):
        return False
    if not question.is_sql:
        return True
    source = next((turn for turn in reversed(earlier) if turn.what is not None), None)
    if source is None:
        return True
    if source.template == question.template and source.what == question.what:
        return False  # the same question again, only reworded
    if source.period and not question.period and question.template not in NO_PERIOD_KINDS:
        return False
    if source.what and not question.what:
        return False
    return True


def _length(rng: random.Random, least: int = 1) -> int:
    lengths = [(n, share) for n, share in LENGTHS if n >= least]
    return rng.choices([n for n, _ in lengths], [share for _, share in lengths])[0]


def _pick(rng: random.Random, pool: list[Turn], group: str, want_sql: bool) -> Turn | None:
    """About 80% from the question's language group, the rest from the other one (either, if one is empty)."""
    same = rng.random() < SAME_LANGUAGE
    choices = [t for t in pool if (t.group == group) == same] or pool
    kind = [t for t in choices if t.is_sql == want_sql]
    return rng.choice(kind or choices) if choices else None


def _earlier(rng: random.Random, pool: list[Turn], group: str, count: int, plain: bool = False) -> list[Turn]:
    """`count` earlier turns; a plain chat has only normal questions and answers."""
    if plain:
        pool = [t for t in pool if t.is_sql]
    return [turn for turn in (_pick(rng, pool, group, plain or rng.random() < SQL_SHARE) for _ in range(count))
            if turn]  # fmt: skip


def as_exchanges(pairs: list[tuple[str, str]]) -> list[Exchange]:
    """(question, gold reply) pairs as the app would send them: saved as its answers would be and passed through its
    own `recent_exchanges`, which keeps the last 6 exchanges within 6,000 characters."""
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    messages = []
    for n, (question, reply) in enumerate(pairs):
        messages.append(Message(2 * n, MessageRole.USER, question, when))
        content, details = _answer(reply)
        messages.append(Message(2 * n + 1, MessageRole.ASSISTANT, content, when, details))
    return recent_exchanges(messages, MAX_EXCHANGES, MAX_CHARACTERS)


def _answer(reply: str) -> tuple[str, AnswerDetails]:
    for prefix, kind in (("CLARIFY: ", AnswerKind.CLARIFY), ("REPLY: ", AnswerKind.REPLY)):
        if reply.startswith(prefix):
            return reply[len(prefix):], AnswerDetails(kind)
    if reply == "UNSUPPORTED":
        return "I can't answer that from your receipts.", AnswerDetails(AnswerKind.UNSUPPORTED)
    return "(the answer)", AnswerDetails(AnswerKind.ANSWER, sql=reply)


def _with_history(row: dict, exchanges: list[Exchange], role: str, specs: list[str]) -> dict:
    parts = read_prompt(row["messages"][0]["content"])
    prompt = build_prompt(parts.question, parts.names, parts.today, tuple(exchanges),
                          gender=gender_of(row["labels"]["user"]))  # fmt: skip
    labels = {**row["labels"], "history": len(exchanges), "history_role": role, "history_specs": specs}
    return {"messages": [{"role": "user", "content": prompt}, row["messages"][1]], "labels": labels}


def add_history(rows: list[dict], split: str) -> tuple[list[dict], dict]:
    """The rows (same order) with history added as approved, and a report. Rows that already have history (the
    follow-ups) count as using it."""
    rng = random.Random(f"{SEED}/{split}")
    turns = [_turn(i, row) for i, row in enumerate(rows)]
    by_user = defaultdict(list)
    for turn, row in zip(turns, rows):
        by_user[row["labels"]["user"]].append(turn)
    pools = {user: [t for t in user_turns if can_be_earlier(t)] for user, user_turns in by_user.items()}
    out = list(rows)

    # English follow-ups: older exchanges in front of about a third.
    follow_ups = [t for t in turns if t.kind == "follow_up"]
    english = sorted((t for t in follow_ups if t.group == "english"), key=lambda t: t.spec)
    for turn in rng.sample(english, round(len(english) * FOLLOW_UPS_WITH_OLDER)):
        row = rows[turn.index]
        base = read_prompt(row["messages"][0]["content"]).history
        pool = [t for t in pools[row["labels"]["user"]] if t.spec != turn.spec]
        length = _length(rng, least=2) - len(base)
        for _ in range(TRIES):
            older = _earlier(rng, pool, turn.group, length)
            if older and well_ordered(older):
                break
        else:
            continue
        exchanges = as_exchanges([(t.question, t.reply) for t in older] + [(e.question, e.reply) for e in base])
        kept = older[len(older) - (len(exchanges) - len(base)):] if len(exchanges) > len(base) else []
        if exchanges[-len(base):] == list(base) and kept and well_ordered(kept):
            out[turn.index] = _with_history(row, exchanges, "dependent", [t.spec for t in kept])

    # Stored questions given history they do not need: enough that about 70% of all chats ignore it.
    dependent = len(follow_ups)
    wanted = round(dependent * INDEPENDENT_SHARE / (1 - INDEPENDENT_SHARE))
    versions = defaultdict(list)
    for turn, row in zip(turns, rows):
        versions[turn.spec].append(turn)
    allowed = {spec: len(v) // 3 for spec, v in versions.items()}
    arabizi_left = {spec: sum(t.group == "arabizi" for t in v) for spec, v in versions.items()}
    candidates = sorted((t for t in turns if can_be_given(t, rows[t.index])), key=lambda t: (t.spec, t.index))
    rng.shuffle(candidates)
    given = 0
    for turn in candidates:
        if given == wanted:
            break
        if allowed[turn.spec] == 0 or (turn.group == "arabizi" and arabizi_left[turn.spec] <= 1):
            continue
        pool = [t for t in pools[rows[turn.index]["labels"]["user"]] if t.spec != turn.spec]
        length = _length(rng)  # drawn once, so that retries do not favour short chats
        plain = turn.is_sql and length >= PLAIN_FROM and rng.random() < PLAIN_SHARE
        for _ in range(TRIES):
            earlier = _earlier(rng, pool, turn.group, length, plain)
            if earlier and follows_well(turn, earlier):
                break
        else:
            continue
        exchanges = as_exchanges([(t.question, t.reply) for t in earlier])
        kept = earlier[len(earlier) - len(exchanges):]
        if not follows_well(turn, kept):  # the character limit dropped the oldest; check what is left
            continue
        out[turn.index] = _with_history(rows[turn.index], exchanges, "independent", [t.spec for t in kept])
        allowed[turn.spec] -= 1
        arabizi_left[turn.spec] -= turn.group == "arabizi"
        given += 1

    report = history_report(out)
    low, high = INDEPENDENT_RANGE
    if report["with_history"] and not low <= report["independent_share"] <= high:
        raise HistoryError(f"{split}: {report['independent_share']:.1%} of chats ignore their history, not "
                           f"{low:.0%}-{high:.0%}")  # fmt: skip
    return out, report


def history_report(rows: list[dict]) -> dict:
    with_history = [r for r in rows if r["labels"].get("history") or r["labels"]["kind"] == "follow_up"]
    independent = sum(r["labels"].get("history_role") == "independent" for r in with_history)
    lengths = Counter(r["labels"].get("history", 1) for r in with_history)
    return {"rows": len(rows), "with_history": len(with_history), "independent": independent,
            "independent_share": independent / len(with_history) if with_history else 0.0,
            "lengths": dict(sorted(lengths.items())),
            "kinds": dict(Counter(r["labels"]["kind"] for r in with_history
                                  if r["labels"].get("history_role") == "independent"))}  # fmt: skip
