import pytest

from app.domain.receipts.errors import FileTooLarge, InvalidReceipt, UnsupportedFileType
from app.domain.receipts.files import MAX_FILE_BYTES, content_type_for, extension_for, file_hash, validate_size


def test_allowed_types_map_to_extensions_and_back():
    for content_type in ("image/jpeg", "image/png", "image/webp", "application/pdf"):
        assert content_type_for("7/abc" + extension_for(content_type)) == content_type
    assert extension_for("IMAGE/JPEG") == ".jpg"


@pytest.mark.parametrize("bad", [None, "", "text/plain", "application/zip", "image/gif"])
def test_other_types_are_refused(bad):
    with pytest.raises(UnsupportedFileType):
        extension_for(bad)


def test_size_limits():
    validate_size(1)
    validate_size(MAX_FILE_BYTES)
    with pytest.raises(InvalidReceipt):
        validate_size(0)
    with pytest.raises(FileTooLarge):
        validate_size(MAX_FILE_BYTES + 1)


def test_hash_depends_only_on_content():
    assert file_hash(b"same") == file_hash(b"same")
    assert file_hash(b"same") != file_hash(b"other")
