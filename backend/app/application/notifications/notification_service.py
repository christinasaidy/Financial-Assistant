from dataclasses import dataclass

from app.application.shared.unit_of_work import UnitOfWorkFactory
from app.domain.notifications.errors import NotificationNotFound
from app.domain.notifications.notification import Notification

PAGE_SIZE = 50


@dataclass(frozen=True)
class NotificationList:
    items: list[Notification]  # newest first
    unread_count: int


class NotificationService:
    """The in-app notification list. Notifications are created by the receipt and budget services."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def list_recent(self, user_id: int) -> NotificationList:
        with self._uow(user_id) as work:
            return NotificationList(work.notifications.list_recent(PAGE_SIZE), work.notifications.unread_count())

    def unread_count(self, user_id: int) -> int:
        with self._uow(user_id) as work:
            return work.notifications.unread_count()

    def mark_read(self, user_id: int, notification_id: int) -> None:
        with self._uow(user_id) as work:
            if not work.notifications.mark_read(notification_id):
                raise NotificationNotFound

    def mark_all_read(self, user_id: int) -> int:
        with self._uow(user_id) as work:
            return work.notifications.mark_all_read()
