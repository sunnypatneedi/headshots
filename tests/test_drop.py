"""Drop intake: folders, photos (any case extension), and clear rejections."""
from __future__ import annotations

from pathlib import Path

import pytest

from headshots.drop import (
    IMAGE_EXTS,
    DropItem,
    extension_of,
    is_supported_image_name,
    resolve_drop,
    resolve_paths,
)

ROOT = Path(__file__).resolve().parent.parent
SWIFT = ROOT / "app" / "Sources" / "Headshots" / "DropIntake.swift"


@pytest.mark.parametrize(
    "path,expected",
    [
        ("IMG_4529.JPG", ".jpg"),
        ("IMG_4529.jpg", ".jpg"),
        ("shot.JPEG", ".jpeg"),
        ("shot.jpeg", ".jpeg"),
        ("face.HEIC", ".heic"),
        ("face.heic", ".heic"),
        ("pic.PNG", ".png"),
        ("pic.png", ".png"),
        ("/Users/me/Shoot/IMG_4529.JPG", ".jpg"),
        ("C:\\Photos\\IMG_4529.JPG", ".jpg"),
        ("noext", ""),
        (".hidden", ""),
    ],
)
def test_extension_of_is_case_insensitive(path, expected):
    assert extension_of(path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "IMG_4529.JPG",
        "IMG_4529.jpg",
        "x.JPEG",
        "x.jpeg",
        "a.HEIC",
        "a.heic",
        "b.PNG",
        "b.png",
        "c.TIF",
        "d.webp",
    ],
)
def test_supported_image_names(path):
    assert is_supported_image_name(path)


@pytest.mark.parametrize("path", ["notes.PDF", "clip.MOV", "IMG_4529.AAE", "readme.txt", "noext"])
def test_unsupported_names(path):
    assert not is_supported_image_name(path)


def test_iphone_jpg_drop_selects_parent_folder():
    result = resolve_drop([
        DropItem(path="/Users/sunny/Shoot/IMG_4529.JPG", is_dir=False),
    ])
    assert result.folder == "/Users/sunny/Shoot"
    assert result.from_single_image is True
    assert result.message is None


def test_folder_drop():
    result = resolve_drop([DropItem(path="/Users/sunny/Shoot", is_dir=True)])
    assert result.folder == "/Users/sunny/Shoot"
    assert result.from_single_image is False


def test_multiple_photos_same_folder():
    result = resolve_drop([
        DropItem(path="/Shoot/a.JPG", is_dir=False),
        DropItem(path="/Shoot/b.heic", is_dir=False),
        DropItem(path="/Shoot/c.png", is_dir=False),
    ])
    assert result.folder == "/Shoot"
    assert result.from_single_image is False


def test_photos_from_different_folders_rejected():
    result = resolve_drop([
        DropItem(path="/A/one.JPG", is_dir=False),
        DropItem(path="/B/two.JPG", is_dir=False),
    ])
    assert result.folder is None
    assert "different folders" in (result.message or "")


def test_unsupported_file_message_names_type():
    result = resolve_drop([DropItem(path="/Shoot/clip.MOV", is_dir=False)])
    assert result.folder is None
    assert "isn’t supported" in (result.message or "")
    assert ".mov" in (result.message or "")


def test_folder_and_file_mix_rejected():
    result = resolve_drop([
        DropItem(path="/Shoot", is_dir=True),
        DropItem(path="/Shoot/IMG_4529.JPG", is_dir=False),
    ])
    assert result.folder is None
    assert "not both" in (result.message or "")


def test_two_folders_rejected():
    result = resolve_drop([
        DropItem(path="/A", is_dir=True),
        DropItem(path="/B", is_dir=True),
    ])
    assert result.folder is None
    assert "one folder" in (result.message or "")


def test_empty_drop():
    result = resolve_drop([])
    assert result.folder is None
    assert result.message


def test_resolve_paths_with_tmpdir(tmp_path: Path):
    photo = tmp_path / "IMG_4529.JPG"
    photo.write_bytes(b"not-a-real-jpeg")
    result = resolve_paths([photo])
    assert result.folder == str(tmp_path)
    assert result.from_single_image is True

    nested = tmp_path / "album"
    nested.mkdir()
    result = resolve_paths([nested])
    assert result.folder == str(nested)


def test_swift_drop_intake_lists_same_extensions():
    assert SWIFT.exists(), "DropIntake.swift missing"
    src = SWIFT.read_text()
    for ext in IMAGE_EXTS:
        bare = ext.lstrip(".")
        assert f'"{bare}"' in src, f"Swift DropIntake missing {bare}"
    assert "resolve" in src
    assert "IMG_4529" in src or "case" in src.lower() or "lowercased" in src
