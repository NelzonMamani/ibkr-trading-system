from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from dataclasses import asdict, is_dataclass

from src.scanner.scanner_runner import run_scanner_cycle


def _to_dict(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return {}


def main() -> None:
    payload = run_scanner_cycle(mode="SIM")
    contexts = payload.get("symbol_context_registry") or {}
    for symbol in sorted(contexts.keys()):
        row = _to_dict(contexts[symbol])
        print("SYMBOL_CONTEXT")
        print("--------------")
        print(f"symbol: {symbol}")
        print(f"pct_change: {row.get('pct_change')}")
        print(f"rvol: {row.get('rvol')}")
        print(f"float: {row.get('float_millions')}M")
        print(f"premarket_high: {row.get('premarket_high')}")
        print(f"prior_close: {row.get('prior_close')}")
        print(f"catalyst: {row.get('news_catalyst')}")


if __name__ == "__main__":
    main()
