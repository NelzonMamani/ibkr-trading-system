from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.scanner.scanner_runner import run_scanner_cycle


def main() -> None:
    payload = run_scanner_cycle(mode="SIM")
    watchlist = payload.get("watchlist_k_symbols") or []
    context_registry = payload.get("symbol_context_registry") or {}
    print(f"WATCHLIST_K={len(watchlist)} symbols={watchlist}")
    print(f"SYMBOL_CONTEXT_CREATED={len(context_registry)}")
    if watchlist and len(context_registry) < len(watchlist):
        missing = sorted(set(watchlist) - set(context_registry.keys()))
        raise SystemExit(f"Missing SymbolContext for: {missing}")


if __name__ == "__main__":
    main()
