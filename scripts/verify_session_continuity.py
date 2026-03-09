from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.prep.premarket_prep import PreMarketPrepEngine


def main() -> None:
    engine = PreMarketPrepEngine()
    engine.update_from_universe(["AAPL", "TSLA"], last_price_by_symbol={"AAPL": 210.0}, session_label="AH", watchlist_symbols={"AAPL", "TSLA"})
    before = engine.build_artifact_payload(["AAPL", "TSLA"]) ["symbols"]
    engine.update_from_universe([], session_label="PRE")
    after = engine.build_artifact_payload(["AAPL", "TSLA"]) ["symbols"]
    print(f"before={[(r['symbol'], r.get('context_status')) for r in before]}")
    print(f"after={[(r['symbol'], r.get('context_status')) for r in after]}")
    retained = [row['symbol'] for row in after if row.get('context_status') == 'retained_context']
    print(f"retained_symbols={retained}")


if __name__ == "__main__":
    main()
