from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from learning.models import LearningDataset
from learning.reporting import build_daily_report, build_summary_text, trade_from_row
from learning.storage import LearningStorage
from storage.serialization import canonical_json
from storage.sqlite_store import SCHEMA_VERSION, SQLiteStore, now_iso


def _insert_run(store: SQLiteStore) -> str:
    run_id = str(uuid4())
    store.insert_run(
        {
            "run_id": run_id,
            "started_at": now_iso(),
            "started_at_utc": now_iso(),
            "ended_at": None,
            "ended_at_utc": None,
            "hostname": "host",
            "user": "tester",
            "app_version": "TEST",
            "git_sha": "deadbeef",
            "run_mode": "PAPER",
            "effective_run_mode": "PAPER",
            "event_replay_mode": "RUN",
            "resolved_config_json": canonical_json({"sample": True}),
            "config_fingerprint": "fingerprint",
            "schema_version": SCHEMA_VERSION,
            "system_version": "TEST",
            "created_at": now_iso(),
        }
    )
    return run_id


def test_learning_report_empty_db(tmp_path):
    db_path = tmp_path / "learning.db"
    storage = LearningStorage(sqlite_path=str(db_path))
    dataset = LearningDataset(trades=[])
    report = build_daily_report(
        asof_date="2026-01-01",
        strategy_name="ROSS_MOMENTUM",
        dataset=dataset,
        watchlists=[],
        trade_reviews=[],
    )
    assert report["executive_summary"]["trades_closed"] == 0
    assert build_summary_text(report)
    storage.close()


def test_learning_report_with_trade_outcome(tmp_path):
    db_path = tmp_path / "learning_with_trade.db"
    store = SQLiteStore(str(db_path))
    store.initialize_schema()
    run_id = _insert_run(store)
    store.insert_trade_outcomes(
        [
            {
                "trade_outcome_id": str(uuid4()),
                "run_id": run_id,
                "cycle_id": None,
                "symbol": "AAPL",
                "trader_type": "MOMENTUM",
                "strategy_name": "ROSS_MOMENTUM",
                "direction": "LONG",
                "entry_price": 10.0,
                "exit_price": 11.0,
                "quantity": 1,
                "gross_realised_pnl": 1.0,
                "commission": 0.0,
                "net_realised_pnl": 1.0,
                "duration_ticks": 1,
                "outcome": "WIN",
                "closed_at": "2026-01-02T14:00:00",
                "payload_json": canonical_json({"sample": True}),
                "created_at": now_iso(),
            }
        ]
    )
    store.close()

    storage = LearningStorage(sqlite_path=str(db_path))
    trades_raw = storage.fetch_trade_outcomes(strategy_name="ROSS_MOMENTUM")
    trades = [trade_from_row(row) for row in trades_raw]
    dataset = LearningDataset(trades=trades)
    report = build_daily_report(
        asof_date="2026-01-02",
        strategy_name="ROSS_MOMENTUM",
        dataset=dataset,
        watchlists=[],
        trade_reviews=[],
    )
    assert report["executive_summary"]["trades_closed"] == 1
    storage.close()
