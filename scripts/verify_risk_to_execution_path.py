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


def _is_real_rejection(status: str, broker_error_code: str | None) -> bool:
    normalized = str(status or "").upper()
    if normalized in {"REJECTED", "FAILED", "BLOCKED", "TIMED_OUT", "CANCELLED", "CANCELED", "INACTIVE", "API_ERROR"}:
        return True
    if broker_error_code and str(broker_error_code) != "2109":
        return True
    return False


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
    print(f"[VERIFY_EXECUTION] probe_symbol={symbol}")

    buy = engine.execute_trade(_decision(symbol=symbol, direction="LONG", decision_id="verify-buy"))
    position_open_after_entry = symbol in engine.position_records
    print(f"[PROBE][EXIT_INTENT] symbol={symbol} side=SELL close_position=True")
    sell = engine.execute_trade(_decision(symbol=symbol, direction="SELL", decision_id="verify-sell"))

    buy_submit_status = _normalize_submit_status(getattr(buy, "status", "UNKNOWN"))
    sell_submit_status = _normalize_submit_status(getattr(sell, "status", "UNKNOWN"))

    fill_ok = int(getattr(buy, "filled_quantity", 0) or 0) >= 1
    exit_filled = int(getattr(sell, "filled_quantity", 0) or 0) >= 1
    position_closed = symbol not in engine.position_records
    exit_recorded = any("EXIT" in stages for stages in engine._order_trace_stages.values()) or exit_filled
    execution_integrity_flag = bool(engine.execution_integrity_flag)

    reason = "PASS_FULL_LIFECYCLE"
    status = "PASS"
    if _is_real_rejection(getattr(buy, "status", ""), getattr(buy, "broker_error_code", None)):
        status, reason = "FAIL", "FAIL_REAL_BROKER_REJECTION"
    elif buy_submit_status not in {"Submitted", "Filled"}:
        status, reason = "FAIL", "FAIL_BUY_NO_ACK"
    elif not fill_ok:
        status, reason = "FAIL", "FAIL_BUY_NOT_FILLED"
    elif not position_open_after_entry:
        status, reason = "FAIL", "FAIL_POSITION_NOT_OPEN_AFTER_BUY"
    elif _is_real_rejection(getattr(sell, "status", ""), getattr(sell, "broker_error_code", None)):
        if "submission limit reached" in str(getattr(sell, "rejection_reason", "")).lower():
            status, reason = "FAIL", "FAIL_EXIT_BLOCKED_BY_GUARD"
        else:
            status, reason = "FAIL", "FAIL_REAL_BROKER_REJECTION"
    elif sell_submit_status not in {"Submitted", "Filled"}:
        status, reason = "FAIL", "FAIL_EXIT_NO_ACK"
    elif not exit_filled:
        status, reason = "FAIL", "FAIL_EXIT_NOT_FILLED"
    elif not position_closed:
        status, reason = "FAIL", "FAIL_POSITION_NOT_CLOSED"
    elif not exit_recorded:
        status, reason = "FAIL", "FAIL_EXIT_NOT_RECORDED"
    elif execution_integrity_flag:
        status, reason = "FAIL", "FAIL_INTEGRITY_MISSING_STAGES"

    print(f"submit_status={buy_submit_status}")
    print(f"exit_submit_status={sell_submit_status}")
    print(f"buy_rejection_reason={getattr(buy, 'rejection_reason', None)}")
    print(f"buy_broker_error_code={getattr(buy, 'broker_error_code', None)}")
    print(f"buy_broker_error_message={getattr(buy, 'broker_error_message', None)}")
    print(f"sell_rejection_reason={getattr(sell, 'rejection_reason', None)}")
    print(f"sell_broker_error_code={getattr(sell, 'broker_error_code', None)}")
    print(f"sell_broker_error_message={getattr(sell, 'broker_error_message', None)}")
    print(f"fill_ok={fill_ok}")
    print(f"position_open={position_open_after_entry}")
    print(f"exit_recorded={exit_recorded}")
    print(f"execution_integrity_flag={execution_integrity_flag}")
    print(f"EXECUTION_PIPELINE_STATUS = {status}")
    print(f"EXECUTION_PIPELINE_REASON = {reason}")

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
