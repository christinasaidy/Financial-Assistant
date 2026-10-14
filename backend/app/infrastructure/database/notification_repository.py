import json

from sqlalchemy import Connection, text

from app.domain.notifications.notification import NewNotification, Notification


class SqlNotificationRepository:
    """Works on a connection already scoped to one user; rows are owned by `app_user_id()`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def add(self, notification: NewNotification) -> bool:
        inserted = self._conn.execute(
            text(
                """
                INSERT INTO notifications (user_id, kind, title, body, data, dedup_key)
                VALUES (app_user_id(), :kind, :title, :body, CAST(:data AS jsonb), :dedup_key)
                ON CONFLICT (user_id, dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING
                RETURNING id
                """
            ),
            {
                "kind": notification.kind.value,
                "title": notification.title,
                "body": notification.body,
                "data": json.dumps(notification.data),
                "dedup_key": notification.dedup_key,
            },
        ).scalar_one_or_none()
        return inserted is not None

    def list_recent(self, limit: int) -> list[Notification]:
        rows = self._conn.execute(
            text(
                "SELECT id, kind, title, body, data, read_at, created_at FROM notifications "
                "ORDER BY created_at DESC, id DESC LIMIT :limit"
            ),
            {"limit": limit},
        ).all()
        return [
            Notification(row.id, row.kind, row.title, row.body, row.data or {}, row.read_at, row.created_at)
            for row in rows
        ]

    def unread_count(self) -> int:
        return self._conn.execute(text("SELECT count(*) FROM notifications WHERE read_at IS NULL")).scalar_one()

    def mark_read(self, notification_id: int) -> bool:
        found = self._conn.execute(
            text("UPDATE notifications SET read_at = COALESCE(read_at, now()) WHERE id = :id RETURNING id"),
            {"id": notification_id},
        ).scalar_one_or_none()
        return found is not None

    def mark_all_read(self) -> int:
        return self._conn.execute(text("UPDATE notifications SET read_at = now() WHERE read_at IS NULL")).rowcount
