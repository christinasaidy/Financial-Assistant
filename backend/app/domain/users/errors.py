from app.domain.shared.errors import DomainError


class InvalidEmail(DomainError):
    default_message = "Enter a valid email address"


class WeakPassword(DomainError):
    default_message = "Password does not meet the requirements"


class InvalidFirstName(DomainError):
    default_message = "Enter a valid first name"


class InvalidGender(DomainError):
    default_message = "Gender must be female, male or prefer_not_to_say"


class EmailAlreadyRegistered(DomainError):
    default_message = "Email is already registered"


class InvalidCredentials(DomainError):
    """Wrong email or password. Deliberately does not say which."""

    default_message = "Invalid email or password"


class InvalidToken(DomainError):
    """The access token is missing, malformed, expired, or not signed by us."""

    default_message = "Invalid or expired token"
