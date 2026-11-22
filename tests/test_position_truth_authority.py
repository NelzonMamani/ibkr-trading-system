from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core.orchestrator import CoreOrchestrator
from src.execution.position_truth import (
    BrokerPositionCollection,
    PositionTruthConfig,
    collect_broker_position_snapshot,
    collect_system_position_snapshot,
    reconcile_position_truth,
)
from src.models.data_models import TradeIntent
from src.ibkr.position_snapshot import BrokerPositionResult


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _reset_overrides():
    set_config_overrides({})
    yield
    set_config_overrides({})


class _BrokerClient:
    def __init__(self, rows):
        self._rows = rows

    def position_snapshot(self):
        for row in self._rows:
            row.account = "TEST"
        return BrokerPositionResult(tuple(self._rows), "COMPLETE", "TEST", _now())


class _NoPositionsClient:
    pass


def test_reconcile_empty_empty_is_healthy() -> None:
    snapshot, verdict = reconcile_position_truth(BrokerPositionCollection(status="COMPLETE", completed_at=_now()), {}, as_of=_now(), live_broker_mode=True)
    assert snapshot.mismatches == []
    assert verdict.healthy is True
    assert verdict.block_new_entries is False
    assert verdict.block_exits is False


def test_reconcile_exact_match_is_healthy() -> None:
    as_of = _now()
    broker = collect_broker_position_snapshot(
        _BrokerClient([SimpleNamespace(symbol="AAPL", position=100, avgCost=100.0)]),
        as_of=as_of,
        config=PositionTruthConfig(broker_required=True, run_mode=RunMode.PAPER),
    )
    system = collect_system_position_snapshot(
        [SimpleNamespace(symbol="AAPL", quantity=100, direction="LONG")],
        as_of=as_of,
    )
    _, verdict = reconcile_position_truth(broker, system, as_of=as_of, live_broker_mode=True)
    assert verdict.healthy is True
    assert verdict.block_new_entries is False


def test_reconcile_broker_only_is_critical() -> None:
    as_of = _now()
    broker = collect_broker_position_snapshot(
        _BrokerClient([SimpleNamespace(symbol="AAPL", position=100)]),
        as_of=as_of,
        config=PositionTruthConfig(broker_required=True, run_mode=RunMode.PAPER),
    )
    _, verdict = reconcile_position_truth(broker, {}, as_of=as_of, live_broker_mode=True)
    assert verdict.healthy is False
    assert verdict.critical_mismatch_count == 1
    assert verdict.block_new_entries is True


def test_reconcile_system_only_is_critical() -> None:
    as_of = _now()
    system = collect_system_position_snapshot(
        [SimpleNamespace(symbol="AAPL", quantity=100, direction="LONG")],
        as_of=as_of,
    )
    _, verdict = reconcile_position_truth(BrokerPositionCollection(status="COMPLETE", completed_at=_now()), system, as_of=as_of, live_broker_mode=True)
    assert verdict.healthy is False
    assert verdict.critical_mismatch_count == 1
    assert verdict.block_new_entries is True


def test_reconcile_quantity_mismatch_is_warning() -> None:
    as_of = _now()
    broker = collect_broker_position_snapshot(
        _BrokerClient([SimpleNamespace(symbol="AAPL", position=100)]),
        as_of=as_of,
        config=PositionTruthConfig(broker_required=True, run_mode=RunMode.PAPER),
    )
    system = collect_system_position_snapshot(
        [SimpleNamespace(symbol="AAPL", quantity=50, direction="LONG")],
        as_of=as_of,
    )
    _, verdict = reconcile_position_truth(broker, system, as_of=as_of, live_broker_mode=True)
    assert verdict.healthy is False
    assert verdict.warning_mismatch_count == 1
    assert verdict.require_reconciliation is True


def test_sim_mode_skips_position_truth_and_never_touches_client_positions(capsys) -> None:
    set_config_overrides({"RUN_MODE": "SIM"})
    orchestrator = CoreOrchestrator()

    verdict = orchestrator._resolve_position_truth_cycle(as_of=_now())

    assert verdict.healthy is True
    assert verdict.require_reconciliation is False
    out = capsys.readouterr().out
    assert "[POSITION][TRUTH][SKIP] run_mode=SIM" in out


def test_orchestrator_entry_guard_blocks_new_intents_when_truth_mismatch() -> None:
    blocked = CoreOrchestrator._apply_position_truth_entry_guard(
        [
            TradeIntent(
                symbol="AAPL",
                direction="LONG",
                strategy_name="ross_momentum",
                confidence=0.9,
                rationale="test",
            )
        ],
        verdict=SimpleNamespace(block_new_entries=True),
    )
    assert blocked == []


def test_dummy_client_without_positions_surfaces_in_paper(capsys) -> None:
    positions = collect_broker_position_snapshot(
        _NoPositionsClient(),
        as_of=_now(),
        config=PositionTruthConfig(broker_required=True, run_mode=RunMode.PAPER),
    )
    assert positions == {}
    out = capsys.readouterr().out
    assert "[POSITION][BROKER_SNAPSHOT][ERROR]" in out

    sim_positions = collect_broker_position_snapshot(
        _NoPositionsClient(),
        as_of=_now(),
        config=PositionTruthConfig(broker_required=False, run_mode=RunMode.SIM),
    )
    assert sim_positions == {}


@pytest.mark.parametrize("quantity", [
    None, False, "", Decimal("1e-1000"), Decimal("1.00000000000000000001"),
])
def test_unavailable_or_lossy_broker_quantity_blocks_new_entries(quantity):
    as_of = _now()
    broker = collect_broker_position_snapshot(
        _BrokerClient([SimpleNamespace(symbol="AAA", position=quantity)]),
        as_of=as_of,
        config=PositionTruthConfig(broker_required=True, run_mode=RunMode.PAPER),
    )
    snapshot, verdict = reconcile_position_truth(broker, {}, as_of=as_of, live_broker_mode=True)
    assert snapshot.snapshot_status == "UNKNOWN"
    assert verdict.block_new_entries


@pytest.mark.parametrize("rows", [
    [SimpleNamespace(symbol="AAA", position=0, con_id=11),
     SimpleNamespace(symbol="AAA", position=1, con_id=22)],
    [SimpleNamespace(symbol="AAA", position=1, con_id=11),
     SimpleNamespace(symbol="BBB", position=1, con_id=11)],
])
def test_ambiguous_broker_security_rows_block_new_entries(rows):
    as_of = _now()
    broker = collect_broker_position_snapshot(
        _BrokerClient(rows), as_of=as_of,
        config=PositionTruthConfig(broker_required=True, run_mode=RunMode.PAPER),
    )
    snapshot, verdict = reconcile_position_truth(broker, {}, as_of=as_of, live_broker_mode=True)
    assert snapshot.snapshot_status == "UNKNOWN"
    assert verdict.block_new_entries


def test_ordinary_fractional_broker_quantity_remains_a_broker_only_veto():
    as_of = _now()
    broker = collect_broker_position_snapshot(
        _BrokerClient([SimpleNamespace(symbol="AAA", position=Decimal("-0.125"), con_id=11)]),
        as_of=as_of,
        config=PositionTruthConfig(broker_required=True, run_mode=RunMode.PAPER),
    )
    snapshot, verdict = reconcile_position_truth(broker, {}, as_of=as_of, live_broker_mode=True)
    assert snapshot.mismatches[0].mismatch_type == "BROKER_ONLY_POSITION"
    assert snapshot.mismatches[0].broker_quantity == -0.125
    assert verdict.block_new_entries
