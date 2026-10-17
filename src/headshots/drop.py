"""Resolve Finder (and similar) drops into a folder the polisher can run on.

The Mac app and this module agree: a folder is used as-is; a supported image
selects its parent folder; mixed parents or unsupported types get a plain message.
Extension checks are case-insensitive (.JPG == .jpg).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

# Keep in sync with app/Sources/Headshots/DropIntake.swift and polish.IMAGE_EXTS.
IMAGE_EXTS = frozenset({
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp",
})


@dataclass(frozen=True)
class DropItem:
    """One dropped path. `is_dir` is supplied by the caller (Finder knows; tests stub it)."""
    path: str
    is_dir: bool


@dataclass(frozen=True)
class DropResult:
    """`folder` is set on success; `message` explains rejection (or notes a single-file pick)."""
    folder: str | None = None
    message: str | None = None
    from_single_image: bool = False


def extension_of(path: str) -> str:
    """Lowercased suffix including the dot, using the final path component only."""
    name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if "." not in name or name.startswith("."):
        # ".bashrc" or no suffix — PurePath treats leading-dot names as suffix-only.
        p = PurePosixPath(name)
        suf = p.suffix
        return suf.lower() if suf and name != suf else ""
    return PurePosixPath(name).suffix.lower()


def is_supported_image_name(path: str) -> bool:
    return extension_of(path) in IMAGE_EXTS


def parent_of(path: str) -> str:
    cleaned = path.replace("\\", "/").rstrip("/")
    if "/" not in cleaned:
        return "."
    parent = cleaned.rsplit("/", 1)[0]
    return parent if parent else "/"


def resolve_drop(items: list[DropItem]) -> DropResult:
    """Turn one or more dropped items into a folder selection or an error message."""
    if not items:
        return DropResult(message="Nothing was dropped.")

    folders = [i for i in items if i.is_dir]
    images = [i for i in items if not i.is_dir and is_supported_image_name(i.path)]
    other = [i for i in items if not i.is_dir and not is_supported_image_name(i.path)]

    if folders and (images or other):
        return DropResult(
            message="Drop a folder, or drop photos — not both at once.",
        )

    if len(folders) > 1:
        return DropResult(message="Drop one folder at a time.")

    if len(folders) == 1:
        return DropResult(folder=_norm(folders[0].path))

    if other and not images:
        names = sorted({extension_of(i.path) or "(none)" for i in other})
        shown = ", ".join(names[:4])
        return DropResult(
            message=f"That file type isn’t supported ({shown}). "
                    f"Drop a folder, or photos: JPG, JPEG, PNG, HEIC.",
        )

    if other and images:
        return DropResult(
            message="Some dropped files aren’t photos. Drop only JPG, JPEG, PNG or HEIC — or a folder.",
        )

    if not images:
        return DropResult(message="Nothing was dropped.")

    parents = sorted({parent_of(i.path) for i in images})
    if len(parents) > 1:
        return DropResult(
            message="Those photos are in different folders. Drop one folder, or photos from the same folder.",
        )

    folder = parents[0]
    return DropResult(
        folder=_norm(folder),
        from_single_image=len(images) == 1,
        message=None,
    )


def _norm(path: str) -> str:
    # Preserve the caller's separators for the Swift side; tests use POSIX.
    if "\\" in path and "/" not in path:
        return str(PureWindowsPath(path))
    return str(PurePosixPath(path))


def resolve_paths(paths: list[Path]) -> DropResult:
    """Filesystem convenience for callers that have real Path objects."""
    items = [DropItem(path=str(p), is_dir=p.is_dir()) for p in paths]
    return resolve_drop(items)
