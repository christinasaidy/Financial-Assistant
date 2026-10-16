from app.domain.shared.errors import DomainError


class InvalidMonth(DomainError):
    default_message = "Choose a month between 1900-01 and 9998-12"
