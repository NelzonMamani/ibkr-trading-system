from __future__ import annotations

import pytest

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core.position_lifecycle_engine import LifecycleIntent, PositionLifecycle, PositionLifecycleEngine, PositionState
from src.core.stop_loss_authority import (
    StopAuditEventType,
    StopAuditTrail,
    StopAuthority,
    StopAuthorityError,
    StopProtectionEvidence,
    StopProtectionStatus,
    StopRecoveryClassification,
    assess_stop_protection,
    classify_stop_recovery,
    validate_stop_price,
    validate_stop_update,
)
from src.execution.post_fill_lifecycle_engine import PostFillLifecycleEngine
from src.storage.storage_engine import StorageEngine


class _ProviderStub:
    def __init__(self) -> None:
        self.stop_calls: list[dict] = []
        self.modify_calls: list[dict] = []
        self.cancel_calls: list[dict] = []

    def place_stop_order(self, **kwargs):
        self.stop_calls.append(dict(kwargs))
        return {"broker_order_id": "STOP-1", "status": "Submitted"}

    def place_target_order(self, **kwargs):
        return {"broker_order_id": "TGT-1", "status": "Submitted"}

    def modify_stop_order(self, **kwargs):
        self.modify_calls.append(dict(kwargs))
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Submitted"}

    def cancel_order(self, **kwargs):
        self.cancel_calls.append(dict(kwargs))
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Cancelled"}


def _authority() -> StopAuthority:
    return StopAuthority(
        symbol="AAPL",
        lifecycle_trade_id="T-1",
        strategy_owner="ross_momentum",
        entry_order_id="ENTRY-1",
        entry_intent_id="INTENT-1",
    )


def test_open_position_without_stop_is_classified_unsafe() -> None:
    assessment = assess_stop_protection(StopProtectionEvidence(symbol="AAPL", state="OPEN"))
    assert assessment["protected"] is False
    assert assessment["status"] == StopProtectionStatus.UNSAFE.value
    assert assessment["reason_code"] == "UNPROTECTED_OPEN_POSITION"


def test_partially_filled_position_requires_protective_stop_handling() -> None:
    raw_assessment = assess_stop_protection(
        StopProtectionEvidence(symbol="AAPL", state="PARTIALLY_FILLED")
    )
    assert raw_assessment["protected"] is False

    engine = PositionLifecycleEngine()
    position = PositionLifecycle(symbol="AAPL", trader_type="SYSTEM")
    result = engine.apply_intent(
        position,
        LifecycleIntent.OPEN,
        requested_quantity=10,
        run_mode=RunMode.LIVE,
        risk_approved=True,
        reason="broker partial",
        filled_quantity_override=4,
        fill_status_override="PARTIAL",
        strategy_owner="ross_momentum",
        entry_order_id="ENTRY-1",
        entry_intent_id="INTENT-1",
    )
    assert result.accepted is True
    assert position.state == PositionState.PARTIALLY_FILLED
    assert position.pending_stop_order_intent == "pending_stop:ENTRY-1"
    assert position.stop_protection_assessment()["status"] == StopProtectionStatus.PENDING.value


def test_valid_long_stop_below_entry_is_accepted() -> None:
    validate_stop_price(side="LONG", stop_price=99.0, entry_price=100.0)


def test_invalid_long_stop_above_entry_is_rejected() -> None:
    with pytest.raises(StopAuthorityError) as excinfo:
        validate_stop_price(side="LONG", stop_price=101.0, entry_price=100.0)
    assert excinfo.value.reason_code == "INVALID_LONG_STOP_PRICE"


def test_stop_tightening_is_allowed() -> None:
    decision = validate_stop_update(
        authority=_authority(),
        requested_by_strategy="ross_momentum",
        side="LONG",
        current_stop_price=95.0,
        candidate_stop_price=98.0,
        entry_price=100.0,
    )
    assert decision["allowed"] is True
    assert decision["tightening"] is True


def test_stop_loosening_rejected_unless_risk_authorized() -> None:
    with pytest.raises(StopAuthorityError) as excinfo:
        validate_stop_update(
            authority=_authority(),
            requested_by_strategy="ross_momentum",
            side="LONG",
            current_stop_price=98.0,
            candidate_stop_price=95.0,
            entry_price=100.0,
        )
    assert excinfo.value.reason_code == "STOP_LOOSENING_REJECTED"

    override = validate_stop_update(
        authority=_authority(),
        requested_by_strategy="ross_momentum",
        side="LONG",
        current_stop_price=98.0,
        candidate_stop_price=95.0,
        entry_price=100.0,
        risk_authorized_override=True,
        override_reason="risk-authority approved wider stop after verified exchange halt",
    )
    assert override["allowed"] is True
    assert override["risk_authorized_override"] is True


def test_another_strategy_cannot_cancel_or_replace_owner_stop() -> None:
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=provider)
    engine.activate_trade_management_after_fill(
        trade_id="T-OWNER",
        symbol="AAPL",
        side="LONG",
        filled_qty=5,
        avg_fill_price=100.0,
        strategy_id="ross_momentum",
    )

    replace = engine.replace_stop(
        trade_id="T-OWNER",
        requested_by_strategy="statistical_intraday_momentum",
        new_stop_price=99.0,
    )
    cancel = engine.cancel_stop(
        trade_id="T-OWNER",
        requested_by_strategy="statistical_intraday_momentum",
        risk_authorized_override=True,
        reason="not owner",
    )
    assert replace["allowed"] is False
    assert replace["reason_code"] == "STOP_OWNERSHIP_CONFLICT"
    assert cancel["allowed"] is False
    assert cancel["reason_code"] == "STOP_OWNERSHIP_CONFLICT"
    assert provider.modify_calls == []
    assert provider.cancel_calls == []


def test_recovery_classifies_missing_stale_orphan_and_matched_stops() -> None:
    flat = classify_stop_recovery(
        lifecycle_stop_order_id=None,
        lifecycle_stop_price=None,
        broker_stop_orders=[],
        symbol="AAPL",
        broker_position_quantity=0,
    )
    matched = classify_stop_recovery(
        lifecycle_stop_order_id="STOP-1",
        lifecycle_stop_price=95.0,
        broker_stop_orders=[{"order_id": "STOP-1", "symbol": "AAPL", "order_type": "STP", "stop_price": 95.0}],
        symbol="AAPL",
        broker_position_quantity=10,
    )
    missing = classify_stop_recovery(
        lifecycle_stop_order_id="STOP-MISSING",
        lifecycle_stop_price=95.0,
        broker_stop_orders=[],
        symbol="AAPL",
        broker_position_quantity=10,
    )
    stale = classify_stop_recovery(
        lifecycle_stop_order_id="STOP-1",
        lifecycle_stop_price=95.0,
        broker_stop_orders=[{"order_id": "STOP-1", "symbol": "AAPL", "order_type": "STP", "stop_price": 94.0}],
        symbol="AAPL",
        broker_position_quantity=10,
    )
    orphan = classify_stop_recovery(
        lifecycle_stop_order_id=None,
        lifecycle_stop_price=None,
        broker_stop_orders=[{"order_id": "STOP-ORPHAN", "symbol": "AAPL", "order_type": "STP", "stop_price": 95.0}],
        symbol="AAPL",
        broker_position_quantity=0,
    )
    short_missing = classify_stop_recovery(
        lifecycle_stop_order_id=None,
        lifecycle_stop_price=None,
        broker_stop_orders=[],
        symbol="AAPL",
        broker_position_quantity=-10,
    )
    short_stale = classify_stop_recovery(
        lifecycle_stop_order_id="STOP-SHORT",
        lifecycle_stop_price=105.0,
        broker_stop_orders=[{"order_id": "STOP-SHORT", "symbol": "AAPL", "order_type": "STP", "stop_price": 106.0}],
        symbol="AAPL",
        broker_position_quantity=-10,
    )
    assert flat["classification"] == StopRecoveryClassification.STOP_MATCH.value
    assert flat["reason_code"] == "flat_no_stop_required"
    assert matched["classification"] == StopRecoveryClassification.STOP_MATCH.value
    assert missing["classification"] == StopRecoveryClassification.STOP_MISSING.value
    assert stale["classification"] == StopRecoveryClassification.STOP_STALE.value
    assert orphan["classification"] == StopRecoveryClassification.STOP_ORPHAN.value
    assert short_missing["classification"] == StopRecoveryClassification.STOP_MISSING.value
    assert short_stale["classification"] == StopRecoveryClassification.STOP_STALE.value


def test_audit_trail_can_reconstruct_stop_lifecycle(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "p2_stop_authority.db"
    monkeypatch.setenv("PERSISTENCE_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("PERSISTENCE_ENABLED", "1")
    monkeypatch.setenv("PERSISTENCE_BACKEND", "sqlite")
    set_config_overrides({})
    storage = StorageEngine()
    try:
        trail = StopAuditTrail(storage_engine=storage)
        authority = _authority()
        trail.record(StopAuditEventType.STOP_REQUIRED, authority, status="REQUIRED", reason="entry_fill")
        trail.record(
            StopAuditEventType.STOP_SUBMITTED,
            authority,
            stop_price=95.0,
            pending_stop_order_intent="stop-submit:T-1",
            status="PENDING_SUBMIT",
        )
        trail.record(
            StopAuditEventType.STOP_ACKNOWLEDGED,
            authority,
            stop_price=95.0,
            active_stop_order_id="STOP-1",
            status="Submitted",
        )
        trail.record(
            StopAuditEventType.STOP_TIGHTENED,
            authority,
            previous_stop_price=95.0,
            stop_price=98.0,
            active_stop_order_id="STOP-1",
        )
        records = storage.fetch_stop_authority_events(lifecycle_trade_id="T-1")
        reconstructed = StopAuditTrail.reconstruct_from_storage(records)
        event_types = [event["event_type"] for event in reconstructed]
        assert StopAuditEventType.STOP_REQUIRED.value in event_types
        assert StopAuditEventType.STOP_SUBMITTED.value in event_types
        assert StopAuditEventType.STOP_ACKNOWLEDGED.value in event_types
        assert StopAuditEventType.STOP_TIGHTENED.value in event_types
        assert reconstructed[-1]["authority"]["strategy_owner"] == "ross_momentum"
    finally:
        storage.shutdown()
        set_config_overrides({})
