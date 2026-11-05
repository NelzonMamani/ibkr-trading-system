"""Synthetic snapshots; real quantity normalization, reconciliation and Core veto."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
from types import SimpleNamespace as NS

import pytest

from src.config.runtime_config import RunMode
from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry
from src.core.managers.connection_manager import ConnectionManager
from src.core.orchestrator import CoreOrchestrator
from src.execution import position_truth as truth
from src.execution.trade_management_engine import TradeManagementEngine
from src.ibkr.position_snapshot import BrokerPositionResult
from src.ibkr.mutation_audit import snapshot as mutations
from test_broker_registry_exposure_admission import no_external_activity
from test_key_level_break_production_handoff import forbid_io
from test_ross_bullflag_micro_management import MemoryStorage


@pytest.fixture
def position_case(monkeypatch):
    class Clock(datetime):
        current=datetime(2026,10,20,13,35,30,tzinfo=timezone.utc)
        @classmethod
        def now(cls,tz=None): return cls.fromtimestamp(cls.current.timestamp(),tz=tz)
    monkeypatch.setattr(truth,"datetime",Clock)
    def reconcile(broker_qty,system_qty):
        result=BrokerPositionResult((NS(symbol="HELD",position=broker_qty,account="SYNTHETIC",con_id=987),),
            "COMPLETE","SYNTHETIC",Clock.current)
        client=NS(position_snapshot=lambda:result)
        broker=truth.collect_broker_position_snapshot(client,as_of=Clock.current,
            config=truth.PositionTruthConfig(broker_required=True,run_mode=RunMode.READ_ONLY))
        system=truth.collect_system_position_snapshot([NS(symbol="HELD",quantity=abs(system_qty),
            direction="SHORT" if system_qty<0 else "LONG")],as_of=Clock.current)
        before=deepcopy((broker,system))
        snapshot,verdict=truth.reconcile_position_truth(broker,system,as_of=Clock.current,live_broker_mode=True)
        assert (broker,system)==before
        assert mutations()=={"place":0,"modify":0,"cancel":0}
        return snapshot,verdict
    return NS(clock=Clock,reconcile=reconcile)


@pytest.mark.parametrize("broker_qty,system_qty,blocked",[
    (3.,2.,True),(2.,3.,False),(-3.,-2.,True),(-2.,-3.,False),
    (.3,.2,True),(.2,.3,False),(-.3,-.2,True),(-.2,-.3,False),
    (2.,2.,False),(-2.,-2.,False),(.125,.125,False),(-.125,-.125,False),
    (math.nextafter(2.,math.inf),2.,True),(2.,math.nextafter(2.,math.inf),False),
    (-math.nextafter(2.,math.inf),-2.,True),(-2.,-math.nextafter(2.,math.inf),False),
])
def test_broker_magnitude_controls_existing_global_veto(position_case,broker_qty,system_qty,blocked):
    snapshot,verdict=position_case.reconcile(broker_qty,system_qty)
    assert verdict.block_new_entries is blocked
    assert not verdict.block_exits
    assert verdict.critical_mismatch_count==0
    assert verdict.warning_mismatch_count==int(broker_qty!=system_qty)
    assert verdict.require_reconciliation==(broker_qty!=system_qty)
    assert verdict.healthy==(broker_qty==system_qty)
    if broker_qty!=system_qty:
        mismatch,=snapshot.mismatches
        assert mismatch.mismatch_type=="QUANTITY_MISMATCH" and mismatch.severity=="WARNING"
        assert mismatch.broker_quantity==broker_qty and mismatch.system_quantity==system_qty
    entries=[NS(symbol="HELD"),NS(symbol="OTHER")]
    assert CoreOrchestrator._apply_position_truth_entry_guard(entries,verdict)==([] if blocked else entries)


@pytest.mark.parametrize("failure",["partial","stale","missing_end","future","disconnect"])
def test_only_fresh_complete_matching_truth_clears_veto(position_case,failure):
    clock=position_case.clock
    state={"qty":3.,"status":"COMPLETE","end":clock.current}
    def snapshot():
        return BrokerPositionResult((NS(symbol="HELD",position=state["qty"],account="SYNTHETIC",con_id=987),),
            state["status"],"SYNTHETIC",state["end"])
    # Actual Core method/ConnectionManager lookup/reconciliation. No risk or
    # entry permission is supplied, and no connection can be initiated.
    core=CoreOrchestrator.__new__(CoreOrchestrator)
    core.run_mode=RunMode.READ_ONLY
    core.connection_manager=ConnectionManager(RunMode.READ_ONLY)
    core.connection_manager._ibkr_connection_manager=NS(existing_client=NS(position_snapshot=snapshot))
    core.trade_registry=ActiveTradeRegistry()
    core.trade_registry.register_trade(ActiveTrade(symbol="HELD",trader_type="SYNTHETIC",entry_tick=0,
        entry_price=10.,direction="LONG",quantity=2,stop_loss_price=9.))
    core.trade_management_engine=TradeManagementEngine(persistence_adapter=MemoryStorage())
    core.execution_engine=NS(_relationship_orders_asof=None,_relationship_open_orders=[])
    core._latest_position_truth_snapshot=None
    core._degraded=False
    before=deepcopy(core.trade_registry.snapshot())
    first=core._resolve_position_truth_cycle(as_of=clock.current)
    assert first.block_new_entries and not first.block_exits and first.warning_mismatch_count==1
    assert core._latest_position_truth_snapshot.broker_positions["HELD"].quantity==3.
    # A matching row is NOT authority without fresh, complete end evidence.
    clock.current+=timedelta(seconds=1)
    state.update(qty=2.,end=clock.current)
    if failure=="partial": state["status"]="TIMEOUT"
    elif failure=="stale": state["end"]=clock.current-timedelta(seconds=truth.get_ibkr_snapshot_max_age_seconds(),microseconds=1)
    elif failure=="missing_end": state["end"]=None
    elif failure=="future": state["end"]=clock.current+timedelta(microseconds=1)
    else: state["status"]="DISCONNECTED"
    unknown=core._resolve_position_truth_cycle(as_of=clock.current)
    assert unknown.block_new_entries and not unknown.healthy
    assert core._latest_position_truth_snapshot.snapshot_status=="UNKNOWN"
    assert core._latest_position_truth_snapshot.broker_positions["HELD"].quantity==3.
    assert core._apply_position_truth_entry_guard([NS(symbol="OTHER")],unknown)==[]
    clock.current+=timedelta(seconds=1)
    state.update(status="COMPLETE",end=clock.current)
    matched=core._resolve_position_truth_cycle(as_of=clock.current)
    assert matched.healthy and not matched.block_new_entries and not matched.require_reconciliation
    assert core._latest_position_truth_snapshot.matched_symbols==["HELD"]
    entries=[NS(symbol="OTHER")]
    assert core._apply_position_truth_entry_guard(entries,matched)==entries
    assert core.trade_registry.snapshot()==before
    assert mutations()=={"place":0,"modify":0,"cancel":0}
