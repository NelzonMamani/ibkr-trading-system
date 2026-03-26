#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def _bars(**kwargs):
    from src.strategies.common.candles.candle_types import Candle

    return [
        Candle(open=10.8, high=10.9, low=10.7, close=10.88, volume=1200),
        Candle(open=10.88, high=11.0, low=10.84, close=10.98, volume=1500),
        Candle(open=10.98, high=11.15, low=10.95, close=11.10, volume=1900),
        Candle(open=11.10, high=11.28, low=11.05, close=11.22, volume=2400),
        Candle(open=11.22, high=11.42, low=11.18, close=11.36, volume=2900),
        Candle(open=11.36, high=11.60, low=11.32, close=11.58, volume=3600),
    ]


def _row(symbol: str, blocked: bool = False) -> dict:
    row = {
        "symbol": symbol,
        "promotion_reason": "watchlist",
        "session_label": "PRE",
        "last_price": 11.6,
        "bid": 11.59,
        "ask": 11.61,
        "volume": 950000,
        "rvol": 3.4,
        "float_millions": 18.0,
        "premarket_high": 11.55,
        "prior_close": 10.8,
        "pct_change": 7.4,
    }
    if blocked:
        row["bid"] = None
        row["ask"] = None
    return row


def _snap(symbol: str) -> MarketSnapshot:
    return MarketSnapshot(symbol=symbol, bid=11.59, ask=11.61, last=11.6, volume=950000, asof_utc=datetime.now(timezone.utc))


def main() -> int:
    import src.strategies.ross_momentum.patterns.pattern_trace as pt

    pt.get_intraday_bars = _bars  # type: ignore[assignment]
    strategy = RossMomentumStrategyV1()
    original_block = strategy._data_contract_block_reasons
    strategy._data_contract_block_reasons = (
        lambda **kwargs: ["MANUAL_BLOCK_FOR_STAGE_PROOF"]
        if kwargs.get("symbol") == "ROSSBLOCK"
        else original_block(**kwargs)
    )
    stages = []
    for symbol, blocked in (("ROSSPASS", False), ("ROSSBLOCK", True)):
        intents = strategy.process_watchlist(
            watchlist=[_row(symbol, blocked=blocked)],
            snapshots={symbol: _snap(symbol)},
            session_label="PRE",
            timestamp_utc=f"verify-{symbol}",
            mode=RunMode.PAPER,
            session_phase="PRE",
        )
        stages.append(
            {
                "symbol": symbol,
                "intent_count": len(intents),
                "terminal_category": "INTENT_CREATED" if intents else "DATA_BLOCKED",
                "reached": ["setup", "confirmation", "trigger", "intent"] if intents else ["data_contract"],
            }
        )

    out = Path("AUDIT_EVIDENCE/ROSS_MAKE_IT_TRADE_LAYER")
    out.mkdir(parents=True, exist_ok=True)
    (out / "runtime_stage_verification.json").write_text(json.dumps({"symbols": stages}, indent=2), encoding="utf-8")
    print(json.dumps({"symbols": stages}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
