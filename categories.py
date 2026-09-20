"""File type categories used by `organize` and `stats`."""
from __future__ import annotations

from pathlib import Path

CATEGORIES: dict[str, set[str]] = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".tiff", ".svg", ".raw", ".ico"},
    "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".3gp"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".csv",
                  ".ppt", ".pptx", ".md", ".epub", ".pages", ".numbers", ".key"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".iso"},
    "Code": {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", ".yml", ".yaml", ".xml",
             ".c", ".cpp", ".h", ".java", ".go", ".rs", ".php", ".rb", ".sh", ".sql", ".ipynb"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".appimage"},
    "Fonts": {".ttf", ".otf", ".woff", ".woff2"},
}

OTHER = "Other"

_LOOKUP = {ext: name for name, exts in CATEGORIES.items() for ext in exts}


def category_for(path: Path) -> str:
    """Return the category name for a file, based on its extension."""
    return _LOOKUP.get(path.suffix.lower(), OTHER)
