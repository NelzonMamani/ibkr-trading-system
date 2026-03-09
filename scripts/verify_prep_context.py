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
    symbols = ["AAPL", "TSLA", "NVDA"]
    engine.update_from_universe(
        symbols,
        last_price_by_symbol={"AAPL": 210.0, "TSLA": 185.2},
        float_by_symbol={"AAPL": 15_600_000_000, "TSLA": 3_200_000_000},
        prior_close_by_symbol={"AAPL": 208.2, "TSLA": 186.4, "NVDA": 120.0},
        persisted_pct_change_by_symbol={"AAPL": 0.85, "TSLA": -0.64},
        persisted_rvol_by_symbol={"AAPL": 1.4, "TSLA": 1.1},
        persisted_volume_by_symbol={"AAPL": 12_000_000, "TSLA": 20_000_000},
        persisted_reference_label_by_symbol={"AAPL": "LAST_RTH_CLOSE"},
        persisted_session_label_by_symbol={"AAPL": "CLOSED"},
        watchlist_symbols={"AAPL", "NVDA"},
        focus_symbols={"AAPL"},
        session_label="CLOSED",
    )
    payload = engine.build_artifact_payload(symbols)
    print(f"symbols={len(payload['symbols'])}")
    sample = payload["symbols"][0]
    print(f"sample_symbol={sample['symbol']} has_float={sample.get('float') is not None} has_news={isinstance(sample.get('news_context'), list)}")
    print(f"sample_fields={sorted(list(sample.keys()))[:8]}...")


if __name__ == "__main__":
    main()
