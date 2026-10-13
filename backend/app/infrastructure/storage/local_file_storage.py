import uuid
from pathlib import Path


class LocalFileStorage:
    """Keeps receipt files on disk under one folder per user. The database stores only the path."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir).resolve()

    def save(self, user_id: int, content: bytes, extension: str) -> str:
        relative = Path(str(user_id)) / f"{uuid.uuid4().hex}{extension}"
        target = self._base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return relative.as_posix()

    def read(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def delete(self, path: str) -> None:
        self._resolve(path).unlink(missing_ok=True)

    def _resolve(self, path: str) -> Path:
        target = (self._base / path).resolve()
        if not target.is_relative_to(self._base):
            raise ValueError("Path is outside the storage folder")
        return target
