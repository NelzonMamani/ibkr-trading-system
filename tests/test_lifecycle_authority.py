from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry
from src.core.orchestrator import CoreOrchestrator
from src.execution.lifecycle_authority import (
    LifecycleStateRecord,
    build_lifecycle_snapshot,
    detect_lifecycle_anomalies,
    evaluate_lifecycle_authority,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _entry_record(symbol: str, state: str, *, age_seconds: int = 0) -> LifecycleStateRecord:
    stamp = _now() - timedelta(seconds=age_seconds)
    return LifecycleStateRecord(
        symbol=symbol,
        trade_id=f"{symbol}-T1",
        broker_order_id=101,
        lifecycle_state=state,
        quantity=10,
        filled_quantity=10 if state == "POSITION_OPEN_CONFIRMED" else 0,
        side="BUY",
        entry_exit_role="ENTRY",
        first_seen_at=stamp,
        last_updated_at=stamp,
        terminal=False,
        rationale="test",
    )


def _exit_record(symbol: str, state: str, *, age_seconds: int = 0, terminal: bool = False) -> LifecycleStateRecord:
    stamp = _now() - timedelta(seconds=age_seconds)
    return LifecycleStateRecord(
        symbol=symbol,
        trade_id=f"{symbol}-X1",
        broker_order_id=201,
        lifecycle_state=state,
        quantity=10,
        filled_quantity=10 if state == "POSITION_CLOSED_CONFIRMED" else 0,
        side="SELL",
        entry_exit_role="EXIT",
        first_seen_at=stamp,
        last_updated_at=stamp,
        terminal=terminal,
        rationale="test",
    )


def test_healthy_entry_lifecycle() -> None:
    records = [_entry_record("AAPL", "POSITION_OPEN_CONFIRMED")]
    anomalies = detect_lifecycle_anomalies(records, as_of=_now())
    verdict = evaluate_lifecycle_authority(records, anomalies)
    assert anomalies == []
    assert verdict.healthy is True


def test_orphan_working_order_blocks_new_entries() -> None:
    records = [_entry_record("AAPL", "ENTRY_WORKING")]
    anomalies = detect_lifecycle_anomalies(records, as_of=_now())
    verdict = evaluate_lifecycle_authority(records, anomalies)
    assert any(a.anomaly_type == "ORPHAN_WORKING_ORDER" for a in anomalies)
    assert verdict.block_new_entries is True


def test_stalled_entry_degrades_verdict(monkeypatch) -> None:
    monkeypatch.setenv("LIFECYCLE_STALL_WARN_SECONDS", "60")
    monkeypatch.setenv("LIFECYCLE_STALL_CRITICAL_SECONDS", "120")
    records = [_entry_record("AAPL", "ENTRY_ACK_PENDING", age_seconds=180)]
    anomalies = detect_lifecycle_anomalies(records, as_of=_now())
    verdict = evaluate_lifecycle_authority(records, anomalies)
    assert any(a.anomaly_type == "STALLED_ENTRY" for a in anomalies)
    assert verdict.healthy is False


def test_stalled_exit_blocks_exit_progression(monkeypatch) -> None:
    monkeypatch.setenv("LIFECYCLE_STALL_WARN_SECONDS", "60")
    monkeypatch.setenv("LIFECYCLE_STALL_CRITICAL_SECONDS", "120")
    records = [_entry_record("AAPL", "POSITION_OPEN_CONFIRMED"), _exit_record("AAPL", "EXIT_WORKING", age_seconds=220)]
    anomalies = detect_lifecycle_anomalies(records, as_of=_now())
    verdict = evaluate_lifecycle_authority(records, anomalies)
    assert any(a.anomaly_type == "STALLED_EXIT" for a in anomalies)
    assert verdict.block_exit_progression is True


def test_position_without_entry_lifecycle_anomaly() -> None:
    records = [_exit_record("AAPL", "POSITION_OPEN_CONFIRMED")]
    records[0].entry_exit_role = "UNKNOWN"
    anomalies = detect_lifecycle_anomalies(records, as_of=_now())
    assert any(a.anomaly_type == "POSITION_WITHOUT_ENTRY_LIFECYCLE" for a in anomalies)


def test_exit_without_position_anomaly() -> None:
    records = [_exit_record("AAPL", "EXIT_WORKING")]
    anomalies = detect_lifecycle_anomalies(records, as_of=_now())
    assert any(a.anomaly_type == "EXIT_WITHOUT_POSITION" for a in anomalies)


def test_terminal_state_enforcement_does_not_auto_close_without_evidence() -> None:
    records = [_entry_record("AAPL", "POSITION_OPEN_CONFIRMED"), _exit_record("AAPL", "EXIT_WORKING", age_seconds=500)]
    anomalies = detect_lifecycle_anomalies(records, as_of=_now())
    assert not any(r.lifecycle_state == "POSITION_CLOSED_CONFIRMED" for r in records)
    assert any(a.anomaly_type in {"STALLED_EXIT", "TERMINAL_STATE_MISSING"} for a in anomalies)


def test_sim_mode_snapshot_is_test_safe() -> None:
    registry = ActiveTradeRegistry()
    registry.register_trade(
        ActiveTrade(
            symbol="AAPL",
            trader_type="sim",
            entry_tick=1,
            entry_price=100.0,
            direction="LONG",
            quantity=5,
            strategy_name="test",
            stop_loss_price=95.0,
        )
    )

    class Deps:
        trade_registry = registry

    records = build_lifecycle_snapshot(Deps(), _now())
    assert len(records) >= 1


def test_orchestrator_integration_blocks_new_entries_when_anomalies_present() -> None:
    records = [_entry_record("AAPL", "ENTRY_WORKING", age_seconds=300)]
    anomalies = detect_lifecycle_anomalies(records, as_of=_now())
    verdict = evaluate_lifecycle_authority(records, anomalies)
    class Intent:
        symbol = "AAPL"

    gated = CoreOrchestrator._apply_lifecycle_entry_guard([Intent()], verdict)
    assert verdict.block_new_entries is True
    assert gated == []
