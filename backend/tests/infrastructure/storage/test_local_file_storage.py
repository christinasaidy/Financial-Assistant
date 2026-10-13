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
