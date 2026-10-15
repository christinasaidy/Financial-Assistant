from app.domain.shared.errors import DomainError


class UnsafeQuery(DomainError):
    """Generated SQL that is not allowed to run: not a single SELECT, or touching something other
    than the assistant views, or calling a function that is not on the allowed list."""

    default_message = "This query is not allowed"


class QueryFailed(DomainError):
    """An allowed query that the database could not run (a wrong column name, a timeout, ...)."""

    default_message = "The query could not be run"


class InvalidQuestion(DomainError):
    default_message = "Type a question"


class ConversationNotFound(DomainError):
    default_message = "Conversation not found"


class MessageNotFound(DomainError):
    default_message = "Message not found"


class CannotRateQuestion(DomainError):
    default_message = "Only the assistant's answers can be rated"
