"""The Standard assistant's memories, managed directly (2026-11-23): list, add, correct and forget them without a
chat. The same rules as when the assistant saves them (app/application/assistant/memory_service.py)."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.api.container import Container
from app.api.dependencies import get_container, get_current_user_id
from app.application.assistant.memory_service import MemoryService
from app.domain.assistant.errors import InvalidMemory, MemoryNotFound
from app.domain.assistant.memory import Memory, MemoryKind
from app.domain.assistant.names import NameKind

router = APIRouter(prefix="/assistant/memories", tags=["assistant"])


class MemoryOut(BaseModel):
    id: int
    kind: str  # "preference" or "alias"
    text: str
    alias: str | None = None
    target_kind: str | None = None  # aliases: "vendor", "item" or "category"
    target_name: str | None = None
    created_at: datetime
    updated_at: datetime
    from_conversation_id: int | None = None  # where it was saved in chat (None once that chat is deleted)

    @classmethod
    def from_memory(cls, memory: Memory) -> "MemoryOut":
        return cls(id=memory.id, kind=memory.kind.value, text=memory.text, alias=memory.alias,
                   target_kind=memory.target_kind.value if memory.target_kind else None,
                   target_name=memory.target_name, created_at=memory.created_at, updated_at=memory.updated_at,
                   from_conversation_id=memory.source_conversation_id)  # fmt: skip


class MemoryIn(BaseModel):
    kind: Literal["preference", "alias"]
    text: str | None = None  # a preference
    alias: str | None = None  # an alias: the user's name ...
    target_kind: Literal["vendor", "item", "category"] | None = None  # ... for one of their names
    target_name: str | None = None


class MemoryUpdateIn(BaseModel):
    text: str | None = None  # a preference's new text
    target_name: str | None = None  # an alias's new target


def _service(container: Container) -> MemoryService:
    if container.memories is None:
        raise MemoryNotFound("Memories are not available")
    return container.memories


@router.get("", response_model=list[MemoryOut])
def list_memories(user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)):
    return [MemoryOut.from_memory(m) for m in _service(container).list_all(user_id)]


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def add_memory(
    body: MemoryIn,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
):
    """201 with the new memory, or 200 with the existing one when it was already saved."""
    service = _service(container)
    if body.kind == MemoryKind.PREFERENCE:
        saved = service.save_preference(user_id, body.text or "")
    elif body.target_kind is None:
        raise InvalidMemory("An alias needs target_kind: vendor, item or category")
    else:
        saved = service.save_alias(user_id, body.alias or "", NameKind(body.target_kind), body.target_name or "")
    if not saved.created:
        response.status_code = status.HTTP_200_OK
    return MemoryOut.from_memory(saved.memory)


@router.patch("/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: int,
    body: MemoryUpdateIn,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
):
    return MemoryOut.from_memory(_service(container).update(user_id, memory_id, body.text, body.target_name))


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def forget_memory(memory_id: int, user_id: int = Depends(get_current_user_id),
                  container: Container = Depends(get_container)) -> Response:  # fmt: skip
    _service(container).forget(user_id, memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
