from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1

OUT = ROOT / "AUDIT_EVIDENCE" / "p01_live_pattern_failure_trace"


def main() -> int:
    strategy = RossMomentumStrategyV1()
    watchlist = [
        {
            "symbol": "TMDE",
            "promotion_reason": "manual_focus",
            "session_label": "AH",
            "last_price": 4.21,
            "bid": 4.2,
            "ask": 4.22,
            "volume": 120000,
            "pct_change": 7.1,
            "rvol": 0.8,
            "float_millions": 12.5,
        },
        {
            "symbol": "TEST",
            "promotion_reason": "manual_focus",
            "session_label": "PRE",
            "last_price": 11.1,
            "bid": 11.09,
            "ask": 11.11,
            "volume": 3000,
            "rvol": 2.0,
            "float_millions": 10.0,
            "premarket_high": 10.95,
            "prior_close": 10.0,
        },
    ]
    snapshots = {
        "TMDE": MarketSnapshot(symbol="TMDE", bid=4.2, ask=4.22, last=4.21, volume=120000, asof_utc=datetime.now(timezone.utc)),
        "TEST": MarketSnapshot(symbol="TEST", bid=11.09, ask=11.11, last=11.1, volume=3000, asof_utc=datetime.now(timezone.utc)),
    }
    intents = strategy.process_watchlist(
        watchlist=watchlist,
        snapshots=snapshots,
        session_label="AH",
        timestamp_utc=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        mode=RunMode.LIVE,
        session_phase="AH",
    )
    evidence_path = OUT / "latest_pattern_failure_trace.json"
    payload = json.loads(evidence_path.read_text())
    assert intents == []
    assert payload["pattern_traces"], "expected pattern traces"
    assert payload["cycle_summaries"], "expected cycle summaries"
    assert any(item["symbol_source"] == "manual_focus" for item in payload["symbol_evaluations"])
    assert any(item["detected_pattern_ids"] for item in payload["symbol_evaluations"]), "expected a detected-and-dropped example"
    print(json.dumps({
        "evidence_path": str(evidence_path),
        "cycle_summaries": payload["cycle_summaries"][-1:],
        "symbol_count": len(payload["symbol_evaluations"]),
        "pattern_trace_count": len(payload["pattern_traces"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
