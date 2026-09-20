"""Find duplicate files by content, cheaply: size -> first 64 KB -> full hash."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .fsutil import iter_files
from .organizer import Move, unique_path

HEAD_BYTES = 64 * 1024
CHUNK = 1024 * 1024


@dataclass
class DuplicateGroup:
    size: int
    paths: list[Path]  # first entry is the copy we keep (oldest, then shortest path)

    @property
    def keep(self) -> Path:
        return self.paths[0]

    @property
    def extras(self) -> list[Path]:
        return self.paths[1:]

    @property
    def wasted(self) -> int:
        return self.size * len(self.extras)


@dataclass
class Result:
    groups: list[DuplicateGroup] = field(default_factory=list)
    scanned: int = 0
    unreadable: int = 0

    @property
    def wasted(self) -> int:
        return sum(g.wasted for g in self.groups)

    @property
    def extra_files(self) -> int:
        return sum(len(g.extras) for g in self.groups)


def _digest(path: Path, head_only: bool = False) -> bytes:
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as f:
        if head_only:
            h.update(f.read(HEAD_BYTES))
        else:
            while chunk := f.read(CHUNK):
                h.update(chunk)
    return h.digest()


def _keep_order(path: Path) -> tuple:
    return (path.stat().st_mtime, len(str(path)), str(path))


def find_duplicates(root: Path, min_size: int = 1, include_hidden: bool = False,
                    exclude: Iterable[Path] = ()) -> Result:
    result = Result()
    by_size: dict[int, list[Path]] = defaultdict(list)
    for path in iter_files(root, include_hidden, exclude):
        try:
            size = path.stat().st_size
        except OSError:
            result.unreadable += 1
            continue
        result.scanned += 1
        if size >= max(min_size, 1):
            by_size[size].append(path)

    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_head: dict[bytes, list[Path]] = defaultdict(list)
        for p in paths:
            try:
                by_head[_digest(p, head_only=True)].append(p)
            except OSError:
                result.unreadable += 1
        for candidates in by_head.values():
            if len(candidates) < 2:
                continue
            by_full: dict[bytes, list[Path]] = defaultdict(list)
            for p in candidates:
                try:
                    by_full[_digest(p)].append(p)
                except OSError:
                    result.unreadable += 1
            for same in by_full.values():
                if len(same) > 1:
                    result.groups.append(DuplicateGroup(size, sorted(same, key=_keep_order)))

    result.groups.sort(key=lambda g: g.wasted, reverse=True)
    return result


def quarantine(extras: list[Path], dest: Path, root: Path) -> list[Move]:
    """Move duplicates into `dest`, keeping their folder layout. Fully undoable."""
    import shutil

    moves: list[Move] = []
    taken: set[Path] = set()
    for src in extras:
        try:
            rel = src.relative_to(root)
        except ValueError:
            rel = Path(src.name)
        target = unique_path(dest / rel, taken)
        taken.add(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(target))
        moves.append(Move(src, target))
    return moves


def delete(extras: list[Path]) -> tuple[int, list[tuple[Path, Exception]]]:
    removed = 0
    errors: list[tuple[Path, Exception]] = []
    for p in extras:
        try:
            p.unlink()
            removed += 1
        except OSError as exc:
            errors.append((p, exc))
    return removed, errors
