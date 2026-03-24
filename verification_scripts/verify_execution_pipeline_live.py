#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.execution.execution_engine import ExecutionEngine
from src.models.data_models import RiskDecision


def _decision(*, symbol: str, direction: str, decision_id: str) -> RiskDecision:
    return RiskDecision(
        symbol=symbol,
        allowed=True,
        max_position_size=1,
        risk_level="LOW",
        rationale="verification probe",
        trader_type="MANUAL",
        strategy_name="LIVE_EXECUTION_PROBE",
        direction=direction,
        decision_id=decision_id,
    )


def main() -> int:
    engine = ExecutionEngine()
    symbol = "UGRO"

    buy = engine.execute_trade(_decision(symbol=symbol, direction="LONG", decision_id="verify-buy"))
    sell = engine.execute_trade(_decision(symbol=symbol, direction="SHORT", decision_id="verify-sell"))
    fill_ok = int(getattr(buy, "filled_quantity", 0) or 0) >= 1
    position_open = symbol in engine.position_records
    exit_recorded = any("EXIT" in stages for stages in engine._order_trace_stages.values()) or int(
        getattr(sell, "filled_quantity", 0) or 0
    ) >= 1
    closed = bool(exit_recorded)

    status = "PASS" if fill_ok and position_open and closed else "FAIL"
    print(f"submit_status={buy.status}")
    print(f"exit_submit_status={sell.status}")
    print(f"fill_ok={fill_ok}")
    print(f"position_open={position_open}")
    print(f"exit_recorded={exit_recorded}")
    print(f"EXECUTION_PIPELINE_STATUS = {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
