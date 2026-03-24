from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.brokers.ibkr_live_broker import IbkrLiveBroker
from src.config.runtime_config import get_run_mode
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import IbkrExecutionProvider
from src.models.data_models import RiskDecision




def _normalize_submit_status(raw_status: str) -> str:
    normalized = str(raw_status or "").upper()
    if normalized in {"ACKED", "ACKNOWLEDGED", "SUBMITTED"}:
        return "Submitted"
    if normalized == "FILLED":
        return "Filled"
    return raw_status

def _decision(symbol: str, direction: str, decision_id: str) -> RiskDecision:
    return RiskDecision(
        symbol=symbol,
        allowed=True,
        max_position_size=1,
        risk_level="LOW",
        rationale="verify_execution_pipeline",
        trader_type="MOMENTUM",
        strategy_name="VerificationHarness",
        direction=direction,
        decision_id=decision_id,
    )


def _build_execution_engine() -> ExecutionEngine:
    """
    Ensure ExecutionEngine is created with a valid IBKR provider.
    Mirrors main system wiring instead of raw constructor.
    """

    mode = get_run_mode()
    print(f"[VERIFY_EXECUTION] run_mode={mode.value}")

    trade_registry = ActiveTradeRegistry()
    event_collector = EventCollector()

    broker = IbkrLiveBroker(
        event_collector=event_collector,
        trade_registry=trade_registry,
        run_mode=mode,
    )
    broker.ensure_connection()

    if broker.connection_manager is None or not broker.connection_manager.is_connected():
        print("[VERIFY_EXECUTION][ERROR] IBKR not connected")
        raise RuntimeError("IBKR connection not established")

    print("[VERIFY_EXECUTION] IBKR connection active")

    provider = IbkrExecutionProvider(
        broker=broker,
        trade_registry=trade_registry,
        run_mode=mode,
    )
    return ExecutionEngine(
        provider=provider,
        trade_registry=trade_registry,
        event_collector=event_collector,
    )


def main() -> int:
    engine = _build_execution_engine()

    symbol = "UGRO"

    buy = engine.execute_trade(_decision(symbol=symbol, direction="LONG", decision_id="verify-buy"))
    sell = engine.execute_trade(_decision(symbol=symbol, direction="SHORT", decision_id="verify-sell"))

    fill_ok = int(getattr(buy, "filled_quantity", 0) or 0) >= 1
    position_open = symbol in engine.position_records
    exit_recorded = any("EXIT" in stages for stages in engine._order_trace_stages.values()) or int(
        getattr(sell, "filled_quantity", 0) or 0
    ) >= 1

    closed = bool(exit_recorded)

    submit_status = _normalize_submit_status(getattr(buy, "status", "UNKNOWN"))
    exit_submit_status = _normalize_submit_status(getattr(sell, "status", "UNKNOWN"))
    no_integrity_flags = not bool(engine.execution_integrity_flag)
    status = "PASS" if (
        fill_ok
        and position_open
        and closed
        and no_integrity_flags
        and submit_status in {"Submitted", "Filled"}
        and exit_submit_status in {"Submitted", "Filled"}
    ) else "FAIL"

    print(f"submit_status={submit_status}")
    print(f"exit_submit_status={exit_submit_status}")
    print(f"fill_ok={fill_ok}")
    print(f"position_open={position_open}")
    print(f"exit_recorded={exit_recorded}")
    print(f"EXECUTION_PIPELINE_STATUS = {status}")

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
