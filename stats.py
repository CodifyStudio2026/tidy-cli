"""Where did my disk space go? Totals per file type plus the biggest files."""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from pathlib import Path

from .categories import category_for
from .fsutil import iter_files


@dataclass
class Stats:
    files: int = 0
    bytes: int = 0
    unreadable: int = 0
    by_category: dict[str, list[int]] = field(default_factory=dict)  # name -> [count, bytes]
    largest: list[tuple[int, Path]] = field(default_factory=list)


def scan(root: Path, top: int = 10, include_hidden: bool = False) -> Stats:
    s = Stats()
    heap: list[tuple[int, str]] = []
    for path in iter_files(root, include_hidden):
        try:
            size = path.stat().st_size
        except OSError:
            s.unreadable += 1
            continue
        s.files += 1
        s.bytes += size
        entry = s.by_category.setdefault(category_for(path), [0, 0])
        entry[0] += 1
        entry[1] += size
        if top:
            item = (size, str(path))
            if len(heap) < top:
                heapq.heappush(heap, item)
            else:
                heapq.heappushpop(heap, item)
    s.largest = [(size, Path(p)) for size, p in sorted(heap, reverse=True)]
    return s
