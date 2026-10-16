from pathlib import Path

import pytest

from app.infrastructure.storage.local_file_storage import LocalFileStorage


def test_save_read_delete(tmp_path):
    storage = LocalFileStorage(tmp_path)
    path = storage.save(7, b"receipt", ".jpg")
    assert path.startswith("7/") and path.endswith(".jpg")
    assert storage.read(path) == b"receipt"
    storage.delete(path)
    assert not (tmp_path / path).exists()
    storage.delete(path)  # deleting twice is fine


def test_each_save_gets_its_own_file(tmp_path):
    storage = LocalFileStorage(tmp_path)
    assert storage.save(7, b"a", ".png") != storage.save(7, b"a", ".png")


@pytest.mark.parametrize("escape", ["../secret.txt", "7/../../secret.txt"])
def test_paths_outside_the_folder_are_refused(tmp_path, escape):
    storage = LocalFileStorage(tmp_path / "uploads")
    with pytest.raises(ValueError):
        storage.read(escape)
    with pytest.raises(ValueError):
        storage.delete(escape)


# --- Second code review (2026-10-16), finding 11: a failed save leaves nothing behind ---


def test_a_write_that_fails_halfway_leaves_no_file(tmp_path, monkeypatch):
    storage = LocalFileStorage(tmp_path)
    real_write_bytes = Path.write_bytes

    def disk_full(self, data):
        real_write_bytes(self, data[:3])  # part of the file reaches the disk, then the write fails
        raise OSError("No space left on device")

    monkeypatch.setattr(Path, "write_bytes", disk_full)
    with pytest.raises(OSError):
        storage.save(7, b"receipt-image", ".jpg")
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []


def test_a_save_that_fails_when_moving_into_place_leaves_no_file(tmp_path, monkeypatch):
    storage = LocalFileStorage(tmp_path)

    def fail(self, target):
        raise OSError("rename failed")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError):
        storage.save(7, b"receipt-image", ".jpg")
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []


def test_only_files_this_storage_named_are_listed(tmp_path):
    storage = LocalFileStorage(tmp_path / "uploads")
    assert storage.user_ids() == []  # no folder yet
    saved = storage.save(7, b"a", ".jpg")
    folder = tmp_path / "uploads" / "7"
    partial = ".partial-" + "0" * 32 + ".pdf"
    (folder / partial).write_bytes(b"half")
    for stranger in ["notes.txt", "0" * 32 + ".jpg.bak", "X" + "0" * 32 + ".jpg"]:
        (folder / stranger).write_bytes(b"not ours")
    (folder / "sub").mkdir()
    (tmp_path / "uploads" / "backups").mkdir()  # not a user folder
    (tmp_path / "uploads" / "backups" / ("0" * 32 + ".jpg")).write_bytes(b"not ours")
    (tmp_path / "outside.jpg").write_bytes(b"not ours")

    assert storage.user_ids() == [7]
    assert sorted(file.path for file in storage.list_files(7)) == sorted([saved, f"7/{partial}"])
    assert storage.list_files(8) == []
    assert all(file.modified_at.tzinfo is not None for file in storage.list_files(7))
