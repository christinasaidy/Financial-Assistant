"""The Standard assistant's memories: listed, saved, corrected and forgotten, by the user's own requests (2026-11-23).

Used both by the Standard model's memory tools (save_memory, update_memory, forget_memory, search_memories) and by the
memory endpoints, so both follow the same rules (app/domain/assistant/memory.py):
- the user comes from the signed-in request; a memory saved in chat records the question it came from;
- an alias's target must be one of the user's names, spelled exactly as their confirmed receipts spell it;
- a repeated request saves nothing new: the same preference or alias is found and returned (also when two requests
  save it at once: the database's unique indexes decide).
"""

from dataclasses import dataclass

from app.application.shared.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.domain.assistant.errors import InvalidMemory, MemoryNotFound, TooManyMemories
from app.domain.assistant.memory import (
    MAX_MEMORIES,
    Memory,
    MemoryKind,
    alias_text,
    clean_alias,
    clean_text,
)
from app.domain.assistant.names import NameKind

MAX_SEARCH_RESULTS = 20


@dataclass(frozen=True)
class MemorySource:
    """The question a memory was asked for in chat."""

    conversation_id: int
    message_id: int


@dataclass(frozen=True)
class SavedMemory:
    memory: Memory
    created: bool  # False: the same memory already existed, and nothing was saved


class MemoryService:
    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def list_all(self, user_id: int) -> list[Memory]:
        with self._uow(user_id) as work:
            return work.memories.list_all()

    def search(self, user_id: int, query: str) -> list[Memory]:
        """Memories whose text or alias contains `query` (ignoring case); all of them for an empty query."""
        wanted = " ".join(query.split()).casefold()
        found = [m for m in self.list_all(user_id)
                 if wanted in m.text.casefold() or wanted in (m.alias or "").casefold()]  # fmt: skip
        return found[:MAX_SEARCH_RESULTS]

    def save_preference(self, user_id: int, text: str, source: MemorySource | None = None) -> SavedMemory:
        text = clean_text(text)
        with self._uow(user_id) as work:
            existing = work.memories.find_preference(text)
            if existing is not None:
                return SavedMemory(existing, created=False)
            _check_room(work)
            memory = work.memories.add(MemoryKind.PREFERENCE, text, *_source(source))
            return SavedMemory(memory or work.memories.find_preference(text), created=memory is not None)

    def save_alias(
        self, user_id: int, alias: str, target_kind: NameKind, target_name: str, source: MemorySource | None = None
    ) -> SavedMemory:
        alias = clean_alias(alias)
        target_name = target_name.strip()
        with self._uow(user_id) as work:
            vendor_id = _check_target(work, target_kind, target_name)
            existing = work.memories.find_alias(alias)
            if existing is not None:
                if (existing.target_kind, existing.target_name) == (target_kind, target_name):
                    return SavedMemory(existing, created=False)
                raise InvalidMemory(f"{alias_text(existing.alias, existing.target_kind, existing.target_name)} is "
                                    f"already saved (memory {existing.id}): update or forget it first")  # fmt: skip
            _check_room(work)
            memory = work.memories.add(MemoryKind.ALIAS, alias_text(alias, target_kind, target_name), *_source(source),
                                       alias=alias, target_kind=target_kind, target_name=target_name,
                                       vendor_id=vendor_id)  # fmt: skip
            return SavedMemory(memory or work.memories.find_alias(alias), created=memory is not None)

    def update(self, user_id: int, memory_id: int, text: str | None = None, target_name: str | None = None) -> Memory:
        """A preference gets a new text; an alias a new target (checked like a new one)."""
        with self._uow(user_id) as work:
            memory = work.memories.get(memory_id)
            if memory is None:
                raise MemoryNotFound
            if memory.kind is MemoryKind.PREFERENCE:
                if not text or target_name:
                    raise InvalidMemory("A preference is corrected with a new text")
                new_text = clean_text(text)
                duplicate = work.memories.find_preference(new_text)
                if duplicate is not None and duplicate.id != memory_id:
                    raise InvalidMemory(f"That preference is already saved (memory {duplicate.id})")
                updated = work.memories.update(memory_id, new_text)
            else:
                if not target_name:
                    raise InvalidMemory("An alias is corrected with a new target name")
                target_name = target_name.strip()
                vendor_id = _check_target(work, memory.target_kind, target_name)
                updated = work.memories.update(memory_id, alias_text(memory.alias, memory.target_kind, target_name),
                                               target_name, vendor_id)  # fmt: skip
            if updated is None:
                raise MemoryNotFound
            return work.memories.get(memory_id) or updated

    def forget(self, user_id: int, memory_id: int) -> None:
        """Deleted for good."""
        with self._uow(user_id) as work:
            if not work.memories.delete(memory_id):
                raise MemoryNotFound


def _check_room(work: UnitOfWork) -> None:
    if work.memories.count() >= MAX_MEMORIES:
        raise TooManyMemories(f"At most {MAX_MEMORIES} memories can be saved: forget one first")


def _check_target(work: UnitOfWork, kind: NameKind, name: str) -> int | None:
    """The vendor id for a shop; raises unless the name is exactly one of the user's."""
    if not name or name not in work.names.existing(kind, [name]):
        raise InvalidMemory(f"'{name}' is not one of the user's {kind.value} names exactly as their receipts spell "
                            "it: find the exact name first")  # fmt: skip
    return work.vendors.find_by_name(name) if kind is NameKind.VENDOR else None


def _source(source: MemorySource | None) -> tuple[int | None, int | None]:
    return (source.conversation_id, source.message_id) if source else (None, None)
