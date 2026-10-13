class DomainError(Exception):
    """Base class for violations of a business rule."""

    default_message = ""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)
