from app.domain.shared.errors import DomainError


class InvalidStateTransition(DomainError):
    def __init__(self, current: object, target: object) -> None:
        super().__init__(f"Cannot move from {current} to {target}")
        self.current = current
        self.target = target


class ReceiptNotFound(DomainError):
    default_message = "Receipt not found"


class DuplicateReceipt(DomainError):
    def __init__(self, existing_id: int) -> None:
        super().__init__("This receipt was already uploaded")
        self.existing_id = existing_id


class UnsupportedFileType(DomainError):
    default_message = "Upload a JPEG, PNG or WebP image, or a PDF"


class FileTooLarge(DomainError):
    default_message = "File is too large"


class InvalidReceipt(DomainError):
    default_message = "Receipt data is not valid"


class ExtractionFailed(DomainError):
    default_message = "The receipt could not be read"
