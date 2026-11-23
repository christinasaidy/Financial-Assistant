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


class InvalidIdempotencyKey(DomainError):
    default_message = "The Idempotency-Key is not valid"


class AssistantModeConflict(DomainError):
    """A question for a conversation that was started in the other mode. A conversation never switches models; to
    use the other mode, start a new conversation."""

    default_message = "This conversation uses the other assistant mode; start a new conversation to switch"


class TurnInProgress(DomainError):
    """The conversation is still answering an earlier question (or the same request is already being answered).
    Nothing new is saved; try again once that answer is in."""

    default_message = "The assistant is still answering a question in this conversation"


class IdempotencyKeyReused(DomainError):
    """The key was already used for a different question, or for a request that failed: send a new key."""

    default_message = "This Idempotency-Key was already used for another request"


class TurnSuperseded(DomainError):
    """Answering took so long that the turn was given up as abandoned; its late answer is not saved."""

    default_message = "This answer took too long and was not saved; ask again"


class InvalidMemory(DomainError):
    default_message = "That cannot be remembered"


class MemoryNotFound(DomainError):
    default_message = "Memory not found"


class TooManyMemories(DomainError):
    default_message = "There are too many saved memories: forget one first"

class DailyLimitReached(DomainError):
    """The user has asked as many Standard questions today as a user may. Nothing is saved; Beta still works."""

    default_message = "You have reached today's limit of Standard questions; try again tomorrow"
