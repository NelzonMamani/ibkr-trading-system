from __future__ import annotations

from pathlib import Path

_PLACEHOLDER_MARKERS = (
    "placeholder",
    "todo",
    "tbd",
    "lorem ipsum",
    "mock evidence",
    "fake evidence",
)


def is_placeholder_evidence(path: Path) -> bool:
    """Return True when an evidence artifact is clearly placeholder content."""
    if not path.exists() or not path.is_file():
        return False

    if path.stat().st_size == 0:
        return True

    name = path.name.lower()
    if "placeholder" in name:
        return True

    try:
        sample = path.read_text(encoding="utf-8", errors="ignore")[:2048].lower()
    except OSError:
        return False

    return any(marker in sample for marker in _PLACEHOLDER_MARKERS)
