from app.domain.shared.errors import DomainError


class UnsafeQuery(DomainError):
    """Generated SQL that is not allowed to run: not a single SELECT, or touching something other
    than the assistant views, or calling a function that is not on the allowed list."""

    default_message = "This query is not allowed"


class QueryFailed(DomainError):
    """An allowed query that the database could not run (a wrong column name, a timeout, ...)."""

    default_message = "The query could not be run"


class QueryRejected(DomainError):
    """Generated SQL that is safe but breaks an answering rule: an item name matched loosely, a name the user
    does not have, or the clock read directly instead of CURRENT_DATE. The model is asked to try again."""

    default_message = "This query does not follow the answering rules"


class UnusableReply(DomainError):
    """A model reply that is not one of the allowed forms, or states a number it was not given."""

    default_message = "The reply cannot be used"


class ModelFailed(DomainError):
    """The language model could not be reached or did not return a usable response."""

    default_message = "The language model did not answer"


class ModelUnavailable(ModelFailed):
    """No language model is configured."""

    default_message = "No language model is configured"


class InvalidQuestion(DomainError):
    default_message = "Type a question"


class ConversationNotFound(DomainError):
    default_message = "Conversation not found"


class MessageNotFound(DomainError):
    default_message = "Message not found"


class CannotRateQuestion(DomainError):
    default_message = "Only the assistant's answers can be rated"
