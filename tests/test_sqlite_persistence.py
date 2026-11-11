from __future__ import annotations

import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from storage.serialization import canonical_json, compute_audit_hash
from storage.sqlite_store import SCHEMA_VERSION, SQLiteStore, now_iso


def _insert_sample_run(store: SQLiteStore, run_id: str) -> None:
    store.insert_run(
        {
            "run_id": run_id,
            "started_at": now_iso(),
            "started_at_utc": now_iso(),
            "ended_at": None,
            "hostname": "host",
            "user": "tester",
            "app_version": "TEST",
            "git_sha": "deadbeef",
            "run_mode": "PAPER",
            "effective_run_mode": "PAPER",
            "event_replay_mode": "CYCLE",
            "resolved_config_json": canonical_json({"sample": True}),
            "config_fingerprint": "fingerprint",
            "schema_version": SCHEMA_VERSION,
            "system_version": "TEST",
            "created_at": now_iso(),
        }
    )


def test_sqlite_persists_run_cycle_events_trade_record(tmp_path):
    db_path = tmp_path / "store.sqlite"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    run_id = str(uuid4())
    _insert_sample_run(store, run_id)

    cycle_id = str(uuid4())
    store.insert_cycle(
        {
            "cycle_id": cycle_id,
            "run_id": run_id,
            "tick": 1,
            "session": "RTH",
            "cycle_started_at": now_iso(),
            "cycle_ended_at": now_iso(),
            "scanner_n": 0,
            "patterns_n": 0,
            "intents_n": 0,
            "risk_n": 0,
            "exec_n": 0,
            "closed_n": 0,
            "created_at": now_iso(),
        }
    )

    payload = {"message": "hello"}
    payload_json = canonical_json(payload)
    event_payload = {
        "run_id": run_id,
        "cycle_id": cycle_id,
        "seq": 1,
        "event_type": "TEST_EVENT",
        "source": "UnitTest",
        "timestamp": now_iso(),
        "payload": json.loads(payload_json),
    }
    event_hash = compute_audit_hash("GENESIS", event_payload)
    store.insert_events(
        [
            {
                "event_id": str(uuid4()),
                "run_id": run_id,
                "cycle_id": cycle_id,
                "event_type": "TEST_EVENT",
                "source": "UnitTest",
                "timestamp": event_payload["timestamp"],
                "payload_json": payload_json,
                "seq": 1,
                "prev_hash": "GENESIS",
                "event_hash": event_hash,
                "created_at": now_iso(),
            }
        ]
    )

    trade_record_id = str(uuid4())
    store.insert_trade_record(
        {
            "trade_record_id": trade_record_id,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "tick": 1,
            "scanner_output_json": "[]",
            "pattern_output_json": "[]",
            "strategy_output_json": "[]",
            "decision_output_json": "[]",
            "risk_output_json": "[]",
            "execution_output_json": "[]",
            "trade_outcomes_json": "[]",
            "performance_snapshot_json": "{}",
            "created_at": now_iso(),
        }
    )

    assert store.fetch_run(run_id) is not None
    assert len(store.fetch_table("cycles", run_id)) == 1
    assert len(store.fetch_table("events", run_id)) == 1
    assert len(store.fetch_table("trade_records", run_id)) == 1

    store.close()


def test_audit_hash_chain_verification_ok(tmp_path):
    db_path = tmp_path / "audit.sqlite"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    run_id = str(uuid4())
    _insert_sample_run(store, run_id)

    cycle_id = str(uuid4())
    store.insert_cycle(
        {
            "cycle_id": cycle_id,
            "run_id": run_id,
            "tick": 1,
            "session": "RTH",
            "cycle_started_at": now_iso(),
            "cycle_ended_at": now_iso(),
            "scanner_n": 0,
            "patterns_n": 0,
            "intents_n": 0,
            "risk_n": 0,
            "exec_n": 0,
            "closed_n": 0,
            "created_at": now_iso(),
        }
    )

    payload = {"message": "audit"}
    payload_json = canonical_json(payload)
    event_payload = {
        "run_id": run_id,
        "cycle_id": cycle_id,
        "seq": 1,
        "event_type": "AUDIT_EVENT",
        "source": "UnitTest",
        "timestamp": now_iso(),
        "payload": json.loads(payload_json),
    }
    event_hash = compute_audit_hash("GENESIS", event_payload)
    store.insert_events(
        [
            {
                "event_id": str(uuid4()),
                "run_id": run_id,
                "cycle_id": cycle_id,
                "event_type": "AUDIT_EVENT",
                "source": "UnitTest",
                "timestamp": event_payload["timestamp"],
                "payload_json": payload_json,
                "seq": 1,
                "prev_hash": "GENESIS",
                "event_hash": event_hash,
                "created_at": now_iso(),
            }
        ]
    )

    result = store.verify_audit_chain(run_id)
    assert result.ok is True

    store.close()


def test_audit_hash_chain_detects_tamper(tmp_path):
    db_path = tmp_path / "tamper.sqlite"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    run_id = str(uuid4())
    _insert_sample_run(store, run_id)

    cycle_id = str(uuid4())
    store.insert_cycle(
        {
            "cycle_id": cycle_id,
            "run_id": run_id,
            "tick": 1,
            "session": "RTH",
            "cycle_started_at": now_iso(),
            "cycle_ended_at": now_iso(),
            "scanner_n": 0,
            "patterns_n": 0,
            "intents_n": 0,
            "risk_n": 0,
            "exec_n": 0,
            "closed_n": 0,
            "created_at": now_iso(),
        }
    )

    payload = {"message": "tamper"}
    payload_json = canonical_json(payload)
    event_payload = {
        "run_id": run_id,
        "cycle_id": cycle_id,
        "seq": 1,
        "event_type": "TAMPER_EVENT",
        "source": "UnitTest",
        "timestamp": now_iso(),
        "payload": json.loads(payload_json),
    }
    event_hash = compute_audit_hash("GENESIS", event_payload)
    store.insert_events(
        [
            {
                "event_id": str(uuid4()),
                "run_id": run_id,
                "cycle_id": cycle_id,
                "event_type": "TAMPER_EVENT",
                "source": "UnitTest",
                "timestamp": event_payload["timestamp"],
                "payload_json": payload_json,
                "seq": 1,
                "prev_hash": "GENESIS",
                "event_hash": event_hash,
                "created_at": now_iso(),
            }
        ]
    )

    store.connection.execute(
        "UPDATE events SET payload_json = ? WHERE run_id = ?",
        (canonical_json({"message": "evil"}), run_id),
    )
    store.connection.commit()

    result = store.verify_audit_chain(run_id)
    assert result.ok is False
    assert result.first_bad_seq == 1

    store.close()


@pytest.fixture
def native_pair_store(isolated_runtime_schema):
    # Existing copied schema supplies the same real SQLite owner without a
    # second account/outcome ledger or operational runtime.
    store = SQLiteStore(str(isolated_runtime_schema))
    _insert_sample_run(store, "NATIVE-PAIR-RUN")
    prior = dict(lifecycle_trade_id="NATIVE-ROOT", run_id="NATIVE-PAIR-RUN", symbol="JPM",
        side="LONG", strategy_name="RossMomentumStrategyV1", status="OPEN",
        quantity_open=2, quantity_closed=0, entry_avg_price=10.5, gross_realized_pnl=0.,
        stop_price=10., target_price=None, target_quantity=0, target_type=None,
        unrealized_pnl=0., last_mark_price=None, source_order_ids_json="['71']",
        source_execution_ids_json="['ENTRY']", opened_at="2026-10-20T13:35:00+00:00",
        closed_at=None, exit_avg_price=None, realized_pnl_by_exit_reason_json="{}",
        reconciliation_flags_json="[]", drift_flags_json="[]", notes_json="[]",
        take_profit_events_json="[]", created_at=now_iso(), updated_at=now_iso())
    store.upsert_trade_lifecycle_trade(prior)
    event = dict(event_id="EXIT-DELTA", run_id=prior["run_id"], lifecycle_trade_id=prior["lifecycle_trade_id"],
        symbol="JPM", side="LONG", event_type="PARTIAL_EXIT", quantity=1, price=10.25,
        timestamp="2026-10-20T13:36:00+00:00", order_id="72", execution_id="EXIT-EXEC",
        source="native_cached_fill", payload_json=json.dumps({"native_feedback_committed": True}),
        created_at=now_iso())
    candidate = dict(prior, quantity_open=1, quantity_closed=1, status="PARTIALLY_CLOSED",
        gross_realized_pnl=-.25, exit_avg_price=10.25, source_execution_ids_json="['ENTRY','EXIT-EXEC']")
    try:
        yield store, prior, candidate, event
    finally:
        store.close()


def test_native_financial_pair_supersedes_only_mark_drift(native_pair_store):
    store, prior, candidate, event = native_pair_store
    # Represents a mark transaction that committed but lost its acknowledgement.
    store.connection.execute("UPDATE trade_lifecycle_trades SET last_mark_price=10.2, unrealized_pnl=-.6")
    store.connection.commit()
    with pytest.raises(RuntimeError, match="STORED_TRADE_CONFLICT"):
        store.persist_native_lifecycle_feedback(candidate, event, expected_trade=prior)
    assert store.fetch_trade_lifecycle_events("NATIVE-PAIR-RUN") == []
    receipt = store.persist_native_lifecycle_feedback(candidate, event, expected_trade=prior, financial_only=True)
    assert receipt == {"completed": True, "event_id": "EXIT-DELTA", "duplicate": False}
    row = store.fetch_trade_lifecycle_trades("NATIVE-PAIR-RUN")[0]
    assert row["quantity_open"] == 1 and row["gross_realized_pnl"] == -.25
    assert row["last_mark_price"] is None and row["unrealized_pnl"] == 0
    assert row["stop_price"] == 10. and row["target_price"] is None
    assert len(store.fetch_trade_lifecycle_events("NATIVE-PAIR-RUN")) == 1
    # A duplicate's candidate snapshot still needs full equality, even though
    # the expected financial precondition ignores only the two mark fields.
    store.connection.execute("UPDATE trade_lifecycle_trades SET last_mark_price=10.3, unrealized_pnl=-.2")
    store.connection.commit()
    with pytest.raises(RuntimeError, match="STORED_EVENT_CONFLICT"):
        store.persist_native_lifecycle_feedback(candidate, event, expected_trade=prior, financial_only=True)
    assert len(store.fetch_trade_lifecycle_events("NATIVE-PAIR-RUN")) == 1


@pytest.mark.parametrize("column,value", [
    ("quantity_open", 3), ("quantity_closed", 1), ("entry_avg_price", 10.75),
    ("gross_realized_pnl", -.5), ("stop_price", 9.5), ("target_price", 12.),
    ("status", "CLOSED"), ("symbol", "MSFT"), ("side", "SHORT"),
    ("strategy_name", "OtherStrategy"), ("source_execution_ids_json", "['FOREIGN']"),
])
def test_native_financial_pair_rejects_financial_or_ownership_drift(native_pair_store, column, value):
    store, prior, candidate, event = native_pair_store
    store.connection.execute(f"UPDATE trade_lifecycle_trades SET {column}=?", (value,))
    store.connection.commit()
    with pytest.raises(RuntimeError, match="STORED_TRADE_CONFLICT"):
        store.persist_native_lifecycle_feedback(candidate, event, expected_trade=prior, financial_only=True)
    assert store.fetch_trade_lifecycle_trades("NATIVE-PAIR-RUN")[0][column] == value
    assert store.fetch_trade_lifecycle_events("NATIVE-PAIR-RUN") == []


@pytest.mark.parametrize("case", ["mark_event", "uncommitted", "retained_price", "retained_pnl", "bool_mode"])
def test_native_financial_mode_cannot_authorize_valuation_write(native_pair_store, case):
    store, prior, candidate, event = native_pair_store
    mode = True
    if case == "mark_event":
        event["event_type"] = "MARK_PRICE"
    elif case == "uncommitted":
        event["payload_json"] = "{}"
    elif case == "retained_price":
        candidate["last_mark_price"] = 10.3
    elif case == "retained_pnl":
        candidate["unrealized_pnl"] = -.2
    else:
        mode = 1
    with pytest.raises(ValueError, match="COMPARISON_MODE_INVALID|FINANCIAL_SUPERSESSION_INVALID"):
        store.persist_native_lifecycle_feedback(candidate, event, expected_trade=prior, financial_only=mode)
    assert store.fetch_trade_lifecycle_events("NATIVE-PAIR-RUN") == []
    assert store.fetch_trade_lifecycle_trades("NATIVE-PAIR-RUN")[0]["quantity_open"] == 2
