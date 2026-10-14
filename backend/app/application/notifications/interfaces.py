from typing import Protocol

from app.domain.notifications.notification import NewNotification, Notification


class NotificationRepository(Protocol):
    def add(self, notification: NewNotification) -> bool:
        """Save it unless one with the same dedup key was already sent. Returns whether it was saved."""

    def list_recent(self, limit: int) -> list[Notification]:
        """Newest first."""

    def unread_count(self) -> int: ...

    def mark_read(self, notification_id: int) -> bool:
        """Returns False if there is no such notification for this user."""

    def mark_all_read(self) -> int: ...
