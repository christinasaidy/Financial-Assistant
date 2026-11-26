"""What the Standard assistant remembers about a user, across conversations (decisions of 2026-11-23).

- Only what the user explicitly asked it to remember (or confirmed when asked): never a guess or a passing remark.
- A preference is how to answer ("Keep your answers short"). An alias is the user's own name for one of their shops,
  items or categories ("zwz means Zaatar w Zeit"); its target must be one of the user's names, checked when saved.
- Never figures ("I spent $250 this month"): receipts change, so amounts are always read again from them.
- Not the user's gender: the reply forms follow the gender chosen at sign-up.
- Deleting a conversation keeps the memories saved in it; forgetting a memory deletes it.
- The Beta assistant never sees memories: its prompt is its training contract.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.assistant.errors import InvalidMemory
from app.domain.assistant.names import NameKind

MAX_MEMORIES = 50  # per user: all of them go with every Standard question, so they must stay few and short
MAX_TEXT_LENGTH = 300
MAX_ALIAS_LENGTH = 60
# An amount: a number next to a currency ("$250", "250 USD", "300,000 LBP", "50 dollars", "1m lira").
_AMOUNT = re.compile(
    r"([$£€]\s*\d)|(\d[\d.,]*\s*(k|m)?\s*(\$|usd|lbp|ll|l\.l\.|dollars?|lira|liras|leera|ler)\b)", re.IGNORECASE
)


class MemoryKind(StrEnum):
    PREFERENCE = "preference"
    ALIAS = "alias"


@dataclass(frozen=True)
class Memory:
    id: int
    kind: MemoryKind
    text: str  # the memory as a sentence, as the user sees it in their list
    created_at: datetime
    updated_at: datetime
    alias: str | None = None  # aliases only: the user's own name ...
    target_kind: NameKind | None = None  # ... for one of their vendors, items or categories ...
    target_name: str | None = None  # ... spelled exactly as their receipts spell it
    vendor_id: int | None = None  # a vendor target's id (None if that vendor was deleted since)
    source_conversation_id: int | None = None  # where it was saved (None once that conversation is deleted)
    source_message_id: int | None = None


def clean_text(raw: str) -> str:
    text = " ".join(raw.split())
    if not text:
        raise InvalidMemory("A memory needs some text")
    if len(text) > MAX_TEXT_LENGTH:
        raise InvalidMemory(f"A memory can be at most {MAX_TEXT_LENGTH} characters")
    if _AMOUNT.search(text):
        raise InvalidMemory("Amounts are not remembered: they are always read again from the receipts")
    return text


def clean_alias(raw: str) -> str:
    alias = " ".join(raw.split())
    if not alias:
        raise InvalidMemory("An alias needs the name the user uses")
    if len(alias) > MAX_ALIAS_LENGTH:
        raise InvalidMemory(f"An alias can be at most {MAX_ALIAS_LENGTH} characters")
    return alias


def alias_text(alias: str, kind: NameKind, target: str) -> str:
    """How an alias reads in the user's list and in the model's context."""
    what = {NameKind.VENDOR: "the shop", NameKind.ITEM: "the item", NameKind.CATEGORY: "the category"}[kind]
    return f'"{alias}" means {what} "{target}"'
