"""A small on-disk log of every change tidy makes, so it can be undone."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

MAX_RUNS = 30


def home() -> Path:
    return Path(os.environ.get("TIDY_HOME") or Path.home() / ".tidy")


def _file() -> Path:
    return home() / "journal.json"


def load() -> list[dict[str, Any]]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save(runs: list[dict[str, Any]]) -> None:
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(runs[-MAX_RUNS:], ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)  # atomic swap: a crash never leaves a half-written journal


def record(kind: str, root: Path, moves: Iterable) -> dict[str, Any]:
    runs = load()
    run = {
        "id": max((r.get("id", 0) for r in runs), default=0) + 1,
        "kind": kind,
        "time": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "moves": [{"src": str(m.src), "dst": str(m.dst)} for m in moves],
    }
    runs.append(run)
    _save(runs)
    return run


def remove(run_id: int) -> None:
    _save([r for r in load() if r.get("id") != run_id])
