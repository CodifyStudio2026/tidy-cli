"""Tiny terminal helpers: colors, sizes, bars, prompts. No dependencies."""
from __future__ import annotations

import os
import sys

_ENABLED: bool | None = None


def _detect() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        os.system("")  # switches on ANSI escape handling in Windows 10+ consoles
    return os.environ.get("TERM") != "dumb"


def set_color(enabled: bool) -> None:
    global _ENABLED
    _ENABLED = enabled


def _wrap(code: str, text: object) -> str:
    global _ENABLED
    if _ENABLED is None:
        _ENABLED = _detect()
    return f"\033[{code}m{text}\033[0m" if _ENABLED else str(text)


def bold(t: object) -> str: return _wrap("1", t)
def dim(t: object) -> str: return _wrap("2", t)
def red(t: object) -> str: return _wrap("31", t)
def green(t: object) -> str: return _wrap("32", t)
def yellow(t: object) -> str: return _wrap("33", t)
def cyan(t: object) -> str: return _wrap("36", t)


def _unicode_ok() -> bool:
    return "utf" in (getattr(sys.stdout, "encoding", None) or "").lower()


def arrow() -> str:
    return "→" if _unicode_ok() else "->"


def bar(fraction: float, width: int = 20) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * width)
    full, empty = ("█", "░") if _unicode_ok() else ("#", "-")
    return full * filled + empty * (width - filled)


def human_size(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def confirm(question: str) -> bool:
    """Ask a yes/no question. Returns False when there is no interactive terminal."""
    if not sys.stdin.isatty():
        return False
    try:
        answer = input(f"{question} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")
