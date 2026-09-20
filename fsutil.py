"""Filesystem walking shared by several commands."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator


def iter_files(root: Path, include_hidden: bool = False, exclude: Iterable[Path] = ()) -> Iterator[Path]:
    """Yield regular files under `root`, skipping symlinks, hidden entries and excluded folders."""
    excluded = {Path(p).resolve() for p in exclude}
    for dirpath, dirnames, filenames in os.walk(root):
        keep = []
        for d in dirnames:
            if not include_hidden and d.startswith("."):
                continue
            if excluded and (Path(dirpath) / d).resolve() in excluded:
                continue
            keep.append(d)
        dirnames[:] = keep
        for name in filenames:
            if not include_hidden and name.startswith("."):
                continue
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            yield path
