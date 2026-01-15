"""Position sizing helpers for Epoch 5 risk gating."""
from __future__ import annotations


def size_for_mode(mode_label: str, default_size: int = 10) -> int:
    normalized = mode_label.upper()
    if normalized == "LIVE_1SHARE":
        return 1
    return default_size
