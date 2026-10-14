from app.domain.shared.errors import DomainError


class NotificationNotFound(DomainError):
    default_message = "Notification not found"
