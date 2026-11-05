"""Adversarial native-result submission evidence, no routing or broker access."""
import pytest
from test_broker_registry_exposure_admission import no_external_activity
from test_key_level_break_production_handoff import forbid_io
from src.execution.execution_engine import ExecutionEngine
from src.models.execution_result import ExecutionResult


@pytest.mark.parametrize("attempted,status,broker_id,expected",[
    (True,"Submitted",71,True),(True,"PreSubmitted",71,True),(True,"Filled",71,True),
    (False,"Submitted",71,False),(True,"Submitted",None,False),
    (True,"PendingSubmit",71,False),(True,"PendingCancel",71,False),
    (True,"REJECTED",71,False),(True,"SUBMISSION_UNKNOWN",71,False),
    (True,"SIMULATED",None,False),
])
def test_attempt_or_identifier_alone_cannot_manufacture_submission(attempted,status,broker_id,expected):
    result=ExecutionResult(symbol="SYNTH",trader_type="SYNTHETIC",attempted=attempted,
        status=status,rationale="synthetic native result",ibkr_order_id=broker_id,
        acknowledged_at="2026-10-20T13:35:41+00:00")
    assert ExecutionEngine.submission_confirmed(result) is expected


@pytest.mark.parametrize("status,broker_id,acknowledged",[
    ("Submitted",71,True),("Submitted",71,False),("Submitted",None,True),
    ("PendingSubmit",71,True),("REJECTED",71,True),("FAILED",None,False),
])
def test_broker_event_waits_for_actual_submitter_ack(status,broker_id,acknowledged,monkeypatch,no_external_activity):
    from datetime import datetime,timezone
    from types import SimpleNamespace as NS
    from src.adapters.brokers.ibkr.ibkr_order_submitter import SubmissionResult
    from src.brokers.ibkr_live_broker import IbkrLiveBroker
    from src.brokers.base_broker import BrokerOrderRequest
    from src.core.active_trade_registry import ActiveTradeRegistry
    from src.core.event_collector import EventCollector
    from src.config.runtime_config import RunMode
    from src.ibkr.mutation_audit import snapshot as mutations
    collector=EventCollector()
    broker=IbkrLiveBroker.__new__(IbkrLiveBroker)
    broker.event_collector=collector
    broker.trade_registry=ActiveTradeRegistry()
    broker.run_mode=RunMode.PAPER
    broker.ensure_connection=lambda:None  # external already-connected boundary
    now=datetime(2026,10,20,13,35,41,tzinfo=timezone.utc)
    def native_response(order):
        # At this boundary no request result exists yet, much less an ack.
        assert not [e for e in collector._cycle_events if e.event_type=="ORDER_SUBMITTED"]
        return SubmissionResult(client_order_id=order.client_order_id,ibkr_order_id=broker_id,
            status=status,error=None,submitted_at=now,acked_at=now if acknowledged else None,
            filled_quantity=0,remaining_quantity=1,fill_status="NONE")
    broker.submitter=NS(submit_once=native_response)
    request=BrokerOrderRequest(client_order_id="synthetic-request",symbol="SYNTH",direction="LONG",
        quantity=1,order_type="MKT",trader_type="MOMENTUM",strategy_name="RossMomentumStrategyV1",
        stop_loss_price=9.)
    result=broker.place_order(request)
    expected=status=="Submitted" and broker_id is not None and acknowledged
    assert ExecutionEngine.submission_confirmed(result) is expected
    assert len([e for e in collector._cycle_events if e.event_type=="ORDER_SUBMITTED"])==int(expected)
    assert result.filled_quantity==0
    assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}


def test_accepted_status_and_order_id_without_ack_receipt_remain_unconfirmed():
    result=ExecutionResult(symbol="SYNTH",trader_type="SYNTHETIC",attempted=True,
        status="Submitted",rationale="local status only",ibkr_order_id=71)
    assert not ExecutionEngine.submission_confirmed(result)
