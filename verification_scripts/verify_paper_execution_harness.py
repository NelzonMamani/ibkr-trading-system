#!/usr/bin/env python3
"""
Deterministic PAPER verification harness.

Runs three session scenarios (CLOSED, PRE, RTH) using deterministic inputs and
records paper execution outputs to storage. This provides a repeatable pipeline
validation without live dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.config.config_resolver import set_config_overrides
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.execution.execution_engine import ExecutionEngine
from src.models.data_models import TradeIntent, TradeRecord
from src.risk.risk_engine import RiskEngine
from src.scanner.scanner import Scanner
from src.storage.storage_engine import StorageEngine


SCENARIOS = [
    ("CLOSED", 5),
    ("PRE", 10),
    ("RTH", 15),
]


def main() -> int:
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "EXECUTION_ENABLED": True,
            "IBKR_READONLY_ENABLED": False,
            "EVENT_REPLAY_MODE": "OFF",
        }
    )
    try:
        trade_registry = ActiveTradeRegistry()
        events = EventCollector()
        scanner = Scanner(event_collector=events)
        risk_engine = RiskEngine(trade_registry=trade_registry, event_collector=events)
        execution_engine = ExecutionEngine(
            trade_registry=trade_registry,
            event_collector=events,
        )
        storage_engine = StorageEngine()

        candidates = scanner.run_scan_cycle()
        symbol = candidates[0].symbol if candidates else "AAPL"

        for session_label, tick in SCENARIOS:
            execution_engine.current_tick = tick
            intent = TradeIntent(
                symbol=symbol,
                direction="LONG",
                strategy_name="VerificationHarness",
                confidence=0.9,
                rationale=f"Deterministic harness scenario={session_label}",
                trader_type="MANUAL",
                stop_loss_price=99.0,
                take_profit_price=110.0,
                tick=tick,
            )
            decision = risk_engine.evaluate_trade_intent(intent)
            result = execution_engine.execute_trade(decision)
            trade_record = TradeRecord(
                scanner_output=candidates,
                pattern_output=[],
                strategy_output=[intent],
                risk_output=[decision],
                execution_output=[result],
            )
            storage_engine.store_trade_record(
                trade_record,
                cycle_context={
                    "tick": tick,
                    "session": session_label,
                    "cycle_started_at": datetime.now(timezone.utc),
                    "cycle_ended_at": datetime.now(timezone.utc),
                },
                events=events.snapshot_cycle(),
            )
            events.clear_cycle()
            print(
                "[VERIFY] scenario={session} tick={tick} status={status} "
                "filled={filled} remaining={remaining}".format(
                    session=session_label,
                    tick=tick,
                    status=result.status,
                    filled=result.filled_quantity,
                    remaining=result.remaining_quantity,
                )
            )
    finally:
        set_config_overrides(None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
