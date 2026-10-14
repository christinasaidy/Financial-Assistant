from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.api.container import Container
from app.api.dependencies import get_container, get_current_user_id

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    data: dict[str, object]  # e.g. {"receipt_id": 42} or {"category_id": 5, "month": "2026-10"}
    read: bool
    created_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    unread_count: int


class UnreadCountOut(BaseModel):
    unread_count: int


@router.get("", response_model=NotificationListOut)
def list_notifications(
    user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)
) -> NotificationListOut:
    """The 50 most recent notifications, newest first, and how many are unread."""
    result = container.notifications.list_recent(user_id)
    items = [
        NotificationOut(
            id=item.id,
            kind=item.kind,
            title=item.title,
            body=item.body,
            data=item.data,
            read=item.read_at is not None,
            created_at=item.created_at,
        )
        for item in result.items
    ]
    return NotificationListOut(items=items, unread_count=result.unread_count)


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(
    user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)
) -> UnreadCountOut:
    """For the badge on the bell icon."""
    return UnreadCountOut(unread_count=container.notifications.unread_count(user_id))


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(
    notification_id: int,
    user_id: int = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> Response:
    container.notifications.mark_read(user_id, notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(
    user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)
) -> Response:
    container.notifications.mark_all_read(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
