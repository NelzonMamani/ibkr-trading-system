#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.domain.market_snapshot import MarketSnapshot
from src.execution.execution_engine import ExecutionEngine
from src.risk.risk_engine import RiskEngine
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


def main() -> int:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True, "IBKR_READONLY_ENABLED": False})
    try:
        import src.strategies.ross_momentum.patterns.pattern_trace as pt

        pt.get_intraday_bars = _bars  # type: ignore[assignment]
        strategy = RossMomentumStrategyV1()
        symbol = "ROSSPPR"
        watchlist = [{
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
        }]
        snapshots = {
            symbol: MarketSnapshot(
                symbol=symbol,
                bid=11.59,
                ask=11.61,
                last=11.6,
                volume=950000,
                asof_utc=datetime.now(timezone.utc),
            )
        }
        intents = strategy.process_watchlist(
            watchlist=watchlist,
            snapshots=snapshots,
            session_label="PRE",
            timestamp_utc="paper-smoke",
            mode=RunMode.PAPER,
            session_phase="PRE",
        )
        events = EventCollector()
        trade_registry = ActiveTradeRegistry()
        risk = RiskEngine(trade_registry=trade_registry, event_collector=events)
        exe = ExecutionEngine(trade_registry=trade_registry, event_collector=events)
        risk_decisions = [risk.evaluate_trade_intent(intent) for intent in intents]
        execution_results = [exe.execute_trade(decision) for decision in risk_decisions]
        submitted = [r for r in execution_results if bool(getattr(r, "attempted", False))]
        artifact = {
            "symbol": symbol,
            "intent_count": len(intents),
            "risk_count": len(risk_decisions),
            "execution_count": len(execution_results),
            "order_submission_attempts": len(submitted),
            "setup_family_id": getattr(intents[0], "setup_family_id", None) if intents else None,
            "trigger_id": getattr(intents[0], "trigger_id", None) if intents else None,
            "entry_price": getattr(intents[0], "entry_price", None) if intents else None,
            "stop_loss_price": getattr(intents[0], "stop_loss_price", None) if intents else None,
            "execution_statuses": [r.status for r in execution_results],
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        out = Path("AUDIT_EVIDENCE/ROSS_MAKE_IT_TRADE_LAYER")
        out.mkdir(parents=True, exist_ok=True)
        (out / "paper_order_smoke.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        print(json.dumps(artifact, indent=2))
        return 0 if artifact["order_submission_attempts"] > 0 else 2
    finally:
        set_config_overrides(None)


if __name__ == "__main__":
    raise SystemExit(main())
