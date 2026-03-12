from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.manual_focus_loader import load_manual_focus_symbols


def merge_focus(scanner_focus: list[str], manual_focus: list[str], max_symbols: int = 5) -> list[str]:
    active: list[str] = []
    seen: set[str] = set()
    for symbol in list(scanner_focus) + list(manual_focus):
        if symbol in seen:
            continue
        seen.add(symbol)
        active.append(symbol)
    return active[:max(0, max_symbols)]


def main() -> None:
    scanner_focus = ["AIFF", "LWLG"]
    manual_focus = load_manual_focus_symbols()
    active_focus = merge_focus(scanner_focus, manual_focus, max_symbols=5)

    print(f"MANUAL_FOCUS: {manual_focus}")
    print(f"SCANNER_FOCUS: {scanner_focus}")
    print(f"ACTIVE_FOCUS: {active_focus}")


if __name__ == "__main__":
    main()
