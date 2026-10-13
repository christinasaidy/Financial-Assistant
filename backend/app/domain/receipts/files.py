import hashlib

from app.domain.receipts.errors import FileTooLarge, InvalidReceipt, UnsupportedFileType

MAX_FILE_BYTES = 10 * 1024 * 1024

_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
_CONTENT_TYPES = {extension: content_type for content_type, extension in _EXTENSIONS.items()}


def extension_for(content_type: str | None) -> str:
    try:
        return _EXTENSIONS[(content_type or "").lower()]
    except KeyError:
        raise UnsupportedFileType from None


def content_type_for(path: str) -> str:
    for extension, content_type in _CONTENT_TYPES.items():
        if path.lower().endswith(extension):
            return content_type
    raise UnsupportedFileType


def validate_size(size: int) -> None:
    if size == 0:
        raise InvalidReceipt("File is empty")
    if size > MAX_FILE_BYTES:
        raise FileTooLarge(f"File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")


def file_hash(content: bytes) -> str:
    """Identifies a file by its content, for duplicate detection."""
    return hashlib.sha256(content).hexdigest()
