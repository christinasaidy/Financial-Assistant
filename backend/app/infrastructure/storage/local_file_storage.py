import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.application.receipts.interfaces import StoredFile

PARTIAL_PREFIX = ".partial-"  # a file being written; never referenced by a receipt
# The only names this storage ever gives a file: a random 32-hex-digit name with a receipt extension, or the same
# with PARTIAL_PREFIX while it is being written. Anything else in the folder is not ours and is never listed.
_OWN_FILE = re.compile(rf"(?:{re.escape(PARTIAL_PREFIX)})?[0-9a-f]{{32}}\.(?:jpg|png|webp|pdf)")
_USER_FOLDER = re.compile(r"[0-9]+")


class LocalFileStorage:
    """Keeps receipt files on disk under one folder per user. The database stores only the path."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir).resolve()

    def save(self, user_id: int, content: bytes, extension: str) -> str:
        name = f"{uuid.uuid4().hex}{extension}"
        relative = Path(str(int(user_id))) / name
        target = self._base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # Written under a temporary name, then renamed (atomic on the same disk): a save that fails halfway never
        # leaves a partial file under the real name, and the partial one is removed (second code review, 11).
        partial = target.with_name(f"{PARTIAL_PREFIX}{name}")
        try:
            partial.write_bytes(content)
            partial.replace(target)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        return relative.as_posix()

    def user_ids(self) -> list[int]:
        if not self._base.is_dir():
            return []
        return sorted(
            int(folder.name)
            for folder in self._base.iterdir()
            if folder.is_dir() and not folder.is_symlink() and _USER_FOLDER.fullmatch(folder.name)
        )

    def list_files(self, user_id: int) -> list[StoredFile]:
        folder = self._base / str(int(user_id))
        if not folder.is_dir() or folder.is_symlink():
            return []
        files = []
        for file in sorted(folder.iterdir()):
            if not (file.is_file() and not file.is_symlink() and _OWN_FILE.fullmatch(file.name)):
                continue
            try:
                modified = file.stat().st_mtime
            except FileNotFoundError:
                continue  # removed meanwhile (a receipt deleted, another clean-up): nothing left to list
            files.append(StoredFile(f"{int(user_id)}/{file.name}", datetime.fromtimestamp(modified, UTC)))
        return files

    def read(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def delete(self, path: str) -> None:
        self._resolve(path).unlink(missing_ok=True)

    def _resolve(self, path: str) -> Path:
        target = (self._base / path).resolve()
        if not target.is_relative_to(self._base):
            raise ValueError("Path is outside the storage folder")
        return target
