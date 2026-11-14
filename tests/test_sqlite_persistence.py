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


def test_committed_accounting_reads_prior_runs_in_insertion_order(native_pair_store):
    store, prior, _, event = native_pair_store
    store.insert_trade_lifecycle_events([dict(event, event_id="first", timestamp="2026-10-20T14:00:00+00:00")])
    for name, mode in (("second", "PAPER"), ("live", "LIVE"), ("sim", "SIM"), ("readonly", "READ_ONLY")):
        _insert_sample_run(store, name)
        store.connection.execute("UPDATE runs SET run_mode=?, effective_run_mode=? WHERE run_id=?", (mode, mode, name))
        store.connection.commit()
        store.upsert_trade_lifecycle_trade(dict(prior, run_id=name, lifecycle_trade_id=name))
        store.insert_trade_lifecycle_events([dict(event, run_id=name, lifecycle_trade_id=name,
            event_id=name, timestamp="2026-10-20T13:00:00+00:00")])
    store.insert_lifecycle_transitions([dict(transition_id="execution.native_orders.v1:" + mode,
        run_id=prior["run_id"], reason=json.dumps({"mode": mode}), transition_seq=0)
        for mode in ("PAPER", "LIVE")])
    result = store.fetch_committed_lifecycle_accounting(run_mode="PAPER")
    assert {row["lifecycle_trade_id"] for row in result["trades"]} == {prior["lifecycle_trade_id"], "second"}
    assert [row["event_id"] for row in result["events"]] == ["first", "second"]
    assert all(row["effective_run_mode"] == "PAPER" and row["run_metadata_present"] == 1
        and row["event_replay_mode"] == "CYCLE" for row in result["events"])
    assert result["native_states"] == [dict(transition_id="execution.native_orders.v1:PAPER",
        reason=json.dumps({"mode": "PAPER"}))]
    # Existing readers still use their caller-provided run and economic order.
    assert [row["event_id"] for row in store.fetch_trade_lifecycle_events("second")] == ["second"]
    live = store.fetch_committed_lifecycle_accounting(run_mode="LIVE")
    assert [row["event_id"] for row in live["events"]] == ["live"]
    assert live["native_states"][0]["transition_id"] == "execution.native_orders.v1:LIVE"


@pytest.mark.parametrize("missing", ["effective_mode", "invalid_mode", "run_row"])
def test_committed_accounting_exposes_unknown_run_scope(native_pair_store, missing):
    store, prior, _, event = native_pair_store
    store.insert_trade_lifecycle_events([event])
    if missing == "run_row":
        store.connection.execute("PRAGMA foreign_keys=OFF")
        store.connection.execute("DELETE FROM runs WHERE run_id=?", (prior["run_id"],))
    else:
        mode = None if missing == "effective_mode" else "UNRECOGNIZED_MODE"
        store.connection.execute("UPDATE runs SET effective_run_mode=? WHERE run_id=?", (mode, prior["run_id"]))
    store.connection.commit()
    result = store.fetch_committed_lifecycle_accounting(run_mode="PAPER")
    assert len(result["trades"]) == len(result["events"]) == 1
    for row in result["trades"] + result["events"]:
        assert row["run_metadata_present"] == (0 if missing == "run_row" else 1)
        assert row["effective_run_mode"] == ("UNRECOGNIZED_MODE" if missing == "invalid_mode" else None)


def test_committed_accounting_read_allows_query_only_and_changes_nothing(native_pair_store):
    store, _, _, event = native_pair_store
    store.insert_trade_lifecycle_events([event])
    changes = store.connection.total_changes
    statements = []
    store.connection.execute("PRAGMA query_only=ON")
    store.connection.set_trace_callback(statements.append)
    result = store.fetch_committed_lifecycle_accounting(run_mode="PAPER")
    store.connection.set_trace_callback(None)
    assert len(result["events"]) == 1 and not store.connection.in_transaction
    assert store.connection.total_changes == changes
    assert statements[0] == "BEGIN" and statements[-1] == "ROLLBACK"
    assert not any(sql.lstrip().upper().startswith(("COMMIT", "INSERT", "UPDATE", "DELETE")) for sql in statements)


def test_committed_accounting_does_not_commit_or_rollback_caller_transaction(native_pair_store):
    store, prior, _, _ = native_pair_store
    store.connection.execute("BEGIN IMMEDIATE")
    store.connection.execute("UPDATE trade_lifecycle_trades SET gross_realized_pnl=-1")
    with pytest.raises(RuntimeError, match="CALLER_TRANSACTION_ACTIVE"):
        store.fetch_committed_lifecycle_accounting(run_mode="PAPER")
    assert store.connection.in_transaction
    assert store.fetch_trade_lifecycle_trades(prior["run_id"])[0]["gross_realized_pnl"] == -1
    store.connection.rollback()
    assert store.fetch_trade_lifecycle_trades(prior["run_id"])[0]["gross_realized_pnl"] == 0


def test_committed_accounting_uses_one_snapshot_across_concurrent_commit(native_pair_store):
    store, prior, candidate, event = native_pair_store
    assert store.connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    writer = SQLiteStore(store.path)
    commits = []
    def after_trade_read(sql):
        if "FROM trade_lifecycle_events AS accounting" in sql and not commits:
            writer.persist_native_lifecycle_feedback(candidate, event, expected_trade=prior)
            commits.append(event["event_id"])
    store.connection.set_trace_callback(after_trade_read)
    try:
        before = store.fetch_committed_lifecycle_accounting(run_mode="PAPER")
    finally:
        store.connection.set_trace_callback(None)
        writer.close()
    assert commits == [event["event_id"]]
    assert before["trades"][0]["quantity_open"] == 2 and before["events"] == []
    after = store.fetch_committed_lifecycle_accounting(run_mode="PAPER")
    assert after["trades"][0]["quantity_open"] == 1
    assert [row["event_id"] for row in after["events"]] == [event["event_id"]]


def test_committed_accounting_read_error_propagates_and_releases_own_transaction(native_pair_store):
    import sqlite3
    store, _, _, _ = native_pair_store
    store.connection.execute("DROP TABLE trade_lifecycle_events")
    store.connection.commit()
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        store.fetch_committed_lifecycle_accounting(run_mode="PAPER")
    assert not store.connection.in_transaction


@pytest.mark.parametrize("mode", ["SIM", "", True, None])
def test_committed_accounting_requires_explicit_operational_mode(native_pair_store, mode):
    store, _, _, _ = native_pair_store
    with pytest.raises(ValueError, match="RUN_MODE_INVALID"):
        store.fetch_committed_lifecycle_accounting(run_mode=mode)


@pytest.mark.parametrize("case", ["disabled", "other_backend", "no_store"])
def test_committed_accounting_adapter_unavailable_cannot_certify_empty(case):
    from src.storage.storage_engine import StorageEngine
    engine = StorageEngine.__new__(StorageEngine)
    engine.enabled = case != "disabled"
    engine.backend = "jsonl" if case == "other_backend" else "sqlite"
    engine._store = None if case == "no_store" else object()
    with pytest.raises(RuntimeError, match="COMMITTED_ACCOUNTING_STORAGE_UNAVAILABLE"):
        engine.fetch_committed_lifecycle_accounting(run_mode="PAPER")


def test_committed_accounting_adapter_delegates_and_preserves_read_failure(native_pair_store):
    from src.storage.storage_engine import StorageEngine
    engine = StorageEngine.__new__(StorageEngine)
    engine.enabled = True
    engine.backend = "sqlite"
    engine._store = native_pair_store[0]
    result = engine.fetch_committed_lifecycle_accounting(run_mode="PAPER")
    assert len(result["trades"]) == 1 and result["trades"][0]["run_mode"] == "PAPER"
    engine._store.close()
    import sqlite3
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        engine.fetch_committed_lifecycle_accounting(run_mode="PAPER")
