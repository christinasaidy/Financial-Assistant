"""The pilot test questions (data/questions.json), the test set (data/test_questions.json) and the evaluation data's
names (data/seed.json)."""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.domain.assistant.answer import ReplyForm
from app.domain.assistant.prompt import VIEW_CATEGORIES, Exchange, UserNames

DATA_DIR = Path(__file__).resolve().parent / "data"
QUESTIONS_FILE = DATA_DIR / "questions.json"
SEED_FILE = DATA_DIR / "seed.json"
# The held-out seed questions, asked as synthetic user 31 (decided with the user on 2026-11-08).
TEST_QUESTIONS_FILE = DATA_DIR / "test_questions.json"

# Date ranges written once, so every question uses exactly the same SQL for the same period.
_MONTH = "receipt_date >= '{start}' AND receipt_date < '{end}'"
PLACEHOLDERS = {
    "{THIS_MONTH}": "receipt_date >= date_trunc('month', CURRENT_DATE) "
    "AND receipt_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'",
    "{LAST_MONTH}": "receipt_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' "
    "AND receipt_date < date_trunc('month', CURRENT_DATE)",
    "{LAST_WEEK}": "receipt_date >= date_trunc('week', CURRENT_DATE) - INTERVAL '1 week' "
    "AND receipt_date < date_trunc('week', CURRENT_DATE)",
    "{AUGUST}": _MONTH.format(start="2026-08-01", end="2026-09-01"),
    "{SEPTEMBER}": _MONTH.format(start="2026-09-01", end="2026-10-01"),
    "{OCTOBER}": _MONTH.format(start="2026-10-01", end="2026-11-01"),
}
_REPLY_FORMS = {"CLARIFY": ReplyForm.CLARIFY, "UNSUPPORTED": ReplyForm.UNSUPPORTED, "REPLY": ReplyForm.REPLY}


@dataclass(frozen=True)
class Accepted:
    """One answer that counts as correct: a query whose result must match, or a reply type."""

    sql: str | None = None
    reply: ReplyForm | None = None


@dataclass(frozen=True)
class PilotQuestion:
    id: str
    question: str
    language: str  # "en" or "arabizi"
    type: str
    accept: tuple[Accepted, ...]
    history: tuple[Exchange, ...] = ()  # for follow-ups: the earlier questions and the SQL that answered them
    group: str | None = None  # questions in the same group are spellings of the same question


def expand(sql: str) -> str:
    for placeholder, condition in PLACEHOLDERS.items():
        sql = sql.replace(placeholder, condition)
    if "{" in sql:
        raise ValueError(f"Unknown placeholder in: {sql}")
    return sql


def load_questions(path: Path = QUESTIONS_FILE) -> tuple[date, list[PilotQuestion]]:
    """The questions and the date they are asked on. Raises ValueError if the file is malformed."""
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = [_question(entry) for entry in data["questions"]]
    ids = [question.id for question in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("Question ids must be unique")
    return date.fromisoformat(data["today"]), questions


def data_user(path: Path = QUESTIONS_FILE) -> int | None:
    """The synthetic user a questions file is asked as (its "user"), or None for the pilot's own data (seed.json)."""
    return json.loads(path.read_text(encoding="utf-8")).get("user")


def seed_names(path: Path = SEED_FILE, categories: tuple[str, ...] = ()) -> UserNames:
    """The names the evaluation user's receipts contain, to check the expected SQL with the answering rules."""
    data = json.loads(path.read_text(encoding="utf-8"))
    receipts = data["receipts"]
    items = sorted({line[0] for receipt in receipts for line in receipt["lines"]})
    vendors = sorted({receipt["vendor"] for receipt in receipts})
    used = {receipt["category"] for receipt in receipts}
    return UserNames(items, vendors, sorted(used | set(categories)) + list(VIEW_CATEGORIES))


def _question(entry: dict) -> PilotQuestion:
    accept = tuple(_accepted(item) for item in entry["accept"])
    if not accept:
        raise ValueError(f"{entry['id']}: no accepted answer")
    history = tuple(Exchange(turn["question"], expand(turn["sql"])) for turn in entry.get("history", ()))
    return PilotQuestion(entry["id"], entry["question"], entry["language"], entry["type"], accept, history,
                        entry.get("group"))  # fmt: skip


def _accepted(item: dict) -> Accepted:
    if "sql" in item:
        return Accepted(sql=expand(item["sql"]))
    if item.get("reply") in _REPLY_FORMS:
        return Accepted(reply=_REPLY_FORMS[item["reply"]])
    raise ValueError(f"An accepted answer must be a SQL query or one of {sorted(_REPLY_FORMS)}: {item}")
