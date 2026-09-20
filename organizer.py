"""Plan, execute and undo file moves. Nothing here ever overwrites a file."""
from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .categories import category_for

MODES = ("type", "date", "ext")

# Files that are still being downloaded or written; never touch them.
PARTIAL_SUFFIXES = {".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload"}


@dataclass(frozen=True)
class Move:
    src: Path
    dst: Path


def _bucket(path: Path, mode: str) -> Path:
    if mode == "type":
        return Path(category_for(path))
    if mode == "ext":
        return Path(path.suffix.lower().lstrip(".") or "no-extension")
    if mode == "date":
        dt = datetime.fromtimestamp(path.stat().st_mtime)
        return Path(f"{dt:%Y}") / f"{dt:%m}"
    raise ValueError(f"unknown mode: {mode}")


def unique_path(dst: Path, taken: set[Path] | None = None) -> Path:
    """Return `dst`, or 'name (1).ext', 'name (2).ext'... if it is already used."""
    taken = taken or set()
    if dst not in taken and not dst.exists():
        return dst
    n = 1
    while True:
        candidate = dst.with_name(f"{dst.stem} ({n}){dst.suffix}")
        if candidate not in taken and not candidate.exists():
            return candidate
        n += 1


def plan(root: Path | str, mode: str = "type", min_age: float = 0.0, include_hidden: bool = False) -> list[Move]:
    """Work out where each loose file directly inside `root` should go."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"not a folder: {root}")
    moves: list[Move] = []
    taken: set[Path] = set()
    now = time.time()
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_symlink() or not entry.is_file():
            continue
        if not include_hidden and entry.name.startswith("."):
            continue
        if entry.suffix.lower() in PARTIAL_SUFFIXES:
            continue
        if min_age and now - entry.stat().st_mtime < min_age:
            continue
        dst = unique_path(root / _bucket(entry, mode) / entry.name, taken)
        taken.add(dst)
        moves.append(Move(entry, dst))
    return moves


def execute(moves: list[Move]) -> tuple[list[Move], list[tuple[Move, Exception]]]:
    """Carry out the moves. Returns (done, errors); `done` holds the real destinations."""
    done: list[Move] = []
    errors: list[tuple[Move, Exception]] = []
    for m in moves:
        try:
            dst = unique_path(m.dst)  # re-check: something may have appeared since planning
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(m.src), str(dst))
            done.append(Move(m.src, dst))
        except OSError as exc:
            errors.append((m, exc))
    return done, errors


def _prune_empty(folder: Path, stop: Path) -> None:
    while folder != stop and stop in folder.parents:
        try:
            folder.rmdir()  # only succeeds when the folder is empty
        except OSError:
            return
        folder = folder.parent


def undo(moves: list[Move]) -> tuple[list[Move], list[tuple[Move, str]]]:
    """Put files back where they came from. Returns (restored, skipped_with_reason)."""
    restored: list[Move] = []
    skipped: list[tuple[Move, str]] = []
    for m in reversed(moves):
        if not m.dst.exists():
            skipped.append((m, "file is no longer at its new location"))
            continue
        if m.src.exists():
            skipped.append((m, "something else now exists at the original path"))
            continue
        try:
            m.src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(m.dst), str(m.src))
            restored.append(m)
            _prune_empty(m.dst.parent, m.src.parent)
        except OSError as exc:
            skipped.append((m, str(exc)))
    return restored, skipped
