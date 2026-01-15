from __future__ import annotations

import json
from pathlib import Path
import sys
from uuid import uuid4

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from performance.storage_reports import generate_reports_from_storage
from storage.serialization import canonical_json
from storage.sqlite_store import SCHEMA_VERSION, SQLiteStore, now_iso


def test_performance_reports_epoch4_from_storage(tmp_path):
    db_path = tmp_path / "reports.db"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()

    run_id = str(uuid4())
    cycle_id = str(uuid4())
    now = now_iso()
    store.insert_run(
        {
            "run_id": run_id,
            "started_at": now,
            "started_at_utc": now,
            "ended_at": None,
            "ended_at_utc": None,
            "hostname": "host",
            "user": "tester",
            "app_version": "TEST",
            "git_sha": "deadbeef",
            "run_mode": "SIM",
            "effective_run_mode": "SIM",
            "event_replay_mode": "RUN",
            "resolved_config_json": canonical_json({"sample": True}),
            "config_fingerprint": "fingerprint",
            "schema_version": SCHEMA_VERSION,
            "system_version": "TEST",
            "created_at": now,
        }
    )
    store.insert_cycle(
        {
            "cycle_id": cycle_id,
            "run_id": run_id,
            "tick": 1,
            "session": "REGULAR",
            "market_session": "REGULAR",
            "cycle_started_at": now,
            "cycle_ended_at": now,
            "scanner_n": 0,
            "scanner_candidates_count": 0,
            "patterns_n": 0,
            "patterns_count": 0,
            "signals_count": 0,
            "intents_n": 0,
            "intents_count": 0,
            "risk_n": 0,
            "risk_decisions_count": 0,
            "exec_n": 0,
            "execution_results_count": 0,
            "closed_n": 2,
            "trade_outcomes_count": 2,
            "warnings_json": "[]",
            "created_at": now,
        }
    )
    store.insert_trade_outcomes(
        [
            {
                "trade_outcome_id": str(uuid4()),
                "run_id": run_id,
                "cycle_id": cycle_id,
                "symbol": "AAA",
                "trader_type": "MANUAL",
                "strategy_name": "TEST",
                "direction": "LONG",
                "entry_price": 10.0,
                "exit_price": 12.0,
                "quantity": 1,
                "gross_realised_pnl": 2.0,
                "commission": 0.1,
                "net_realised_pnl": 1.9,
                "duration_ticks": 5,
                "outcome": "WIN",
                "closed_at": now,
                "payload_json": canonical_json({"symbol": "AAA"}),
                "created_at": now,
            },
            {
                "trade_outcome_id": str(uuid4()),
                "run_id": run_id,
                "cycle_id": cycle_id,
                "symbol": "BBB",
                "trader_type": "MANUAL",
                "strategy_name": "TEST",
                "direction": "LONG",
                "entry_price": 20.0,
                "exit_price": 19.0,
                "quantity": 1,
                "gross_realised_pnl": -1.0,
                "commission": 0.1,
                "net_realised_pnl": -1.1,
                "duration_ticks": 5,
                "outcome": "LOSS",
                "closed_at": now,
                "payload_json": canonical_json({"symbol": "BBB"}),
                "created_at": now,
            },
        ]
    )

    snapshot_payload = {
        "total_trades": 2,
        "trade_outcomes": [
            {"exit_category": "EXIT_TARGET"},
            {"exit_category": "EXIT_STOP_LOSS"},
        ],
        "rule_adherence": {"stop_loss_violations": 0},
    }
    store.insert_performance_snapshot(
        {
            "performance_snapshot_id": str(uuid4()),
            "run_id": run_id,
            "cycle_id": cycle_id,
            "tick": 1,
            "payload_json": canonical_json(snapshot_payload),
            "created_at": now,
        }
    )

    artifacts = generate_reports_from_storage(
        store,
        run_id,
        "daily",
        output_dir=str(tmp_path / "reports"),
    )
    with open(artifacts.json_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    assert payload["summary"]["total_trades"] == 2
    assert payload["summary"]["wins"] == 1
    assert payload["summary"]["losses"] == 1
    assert payload["exit_category_distribution"]["EXIT_TARGET"] == 1
    assert payload["rule_adherence"]["stop_loss_violations"] == 0

    store.close()
