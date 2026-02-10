import json
import time

import pytest

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.core.stop_controller import StopMode
from src.scanner.providers.base import ProviderConnectionError
from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec
from src.strategies.statistical_intraday_momentum.strategy_policy import (
    statistical_stock_selection_spec,
)


def _reset_overrides():
    set_config_overrides(None)


@pytest.fixture(autouse=True)
def _cleanup_overrides():
    yield
    _reset_overrides()


def test_trace_event_order_sim(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_LOG_DIR", str(tmp_path))
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "SELECTED_STRATEGY": "ross_momentum",
        }
    )

    orchestrator = CoreOrchestrator()
    assert orchestrator.run_once() is True

    log_files = list(tmp_path.glob("trace_*.jsonl"))
    assert log_files, "trace log file missing"

    cycle_id = orchestrator._current_cycle_id
    stages = []
    for line in log_files[0].read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("cycle_id") == cycle_id:
            stages.append(record.get("stage"))

    assert "UNIVERSE" in stages
    assert "WATCHLIST" in stages
    assert "FOCUS" in stages
    assert "ACTION" in stages
    assert stages.index("UNIVERSE") < stages.index("WATCHLIST") < stages.index("FOCUS") < stages.index("ACTION")


def test_trace_schema_completeness_and_reconstruction(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_LOG_DIR", str(tmp_path))
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "SELECTED_STRATEGY": "ross_momentum",
        }
    )

    orchestrator = CoreOrchestrator()
    assert orchestrator.run_once() is True

    log_files = list(tmp_path.glob("trace_*.jsonl"))
    assert log_files, "trace log file missing"

    cycle_id = orchestrator._current_cycle_id
    records = []
    for line in log_files[0].read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("cycle_id") == cycle_id:
            records.append(record)

    assert records, "no trace records found for cycle"

    required_fields = {
        "event_id",
        "timestamp",
        "event_type",
        "stage",
        "component",
        "entity_id",
        "parent_event_id",
        "cycle_id",
        "run_mode",
        "strategy",
        "metadata",
    }
    seen_event_ids = set()
    for record in records:
        for field in required_fields:
            assert field in record, f"missing trace field: {field}"
        assert record["timestamp"], "missing timestamp"
        if seen_event_ids:
            assert record["parent_event_id"] in seen_event_ids
        else:
            assert record["parent_event_id"] is None
        seen_event_ids.add(record["event_id"])

    stages = [record.get("stage") for record in records]
    for stage in ("UNIVERSE", "WATCHLIST", "FOCUS", "ACTION"):
        assert stage in stages, f"missing trace stage: {stage}"

    action_record = next(record for record in records if record.get("stage") == "ACTION")
    record_map = {record["event_id"]: record for record in records}
    chain_stages = []
    current = action_record
    visited = set()
    while current and current["event_id"] not in visited:
        visited.add(current["event_id"])
        chain_stages.append(current["stage"])
        parent_id = current.get("parent_event_id")
        if parent_id is None:
            break
        current = record_map.get(parent_id)

    ordered_chain = list(reversed(chain_stages))
    last_index = -1
    for stage in ("UNIVERSE", "WATCHLIST", "FOCUS", "ACTION"):
        assert stage in ordered_chain, f"missing reconstructed stage: {stage}"
        idx = ordered_chain.index(stage)
        assert idx > last_index, f"trace stage out of order: {stage}"
        last_index = idx


def test_live_readonly_connectivity_retry(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TRACE_LOG_DIR", str(tmp_path))
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "IBKR_FALLBACK_ENABLED": False,
        }
    )

    def fake_connect(self):
        raise ProviderConnectionError("IBKR down")

    monkeypatch.setattr(
        "src.scanner.providers.ibkr_provider.IbkrScannerProvider.connect", fake_connect
    )

    orchestrator = CoreOrchestrator()

    def fake_sleep(_seconds):
        orchestrator.stop_controller.request_stop(
            StopMode.GRACEFUL, reason="test", source="test"
        )

    monkeypatch.setattr(time, "sleep", fake_sleep)

    orchestrator.run_forever(max_cycles=None, cycle_sleep_seconds=0)
    output = capsys.readouterr().out
    assert "STATE=DEGRADED" in output

    log_files = list(tmp_path.glob("trace_*.jsonl"))
    assert log_files, "trace log file missing"

    halt_lines = []
    for line in log_files[0].read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("stage") == "HALT":
            halt_lines.append(record)
    assert halt_lines, "HALT trace missing"


def test_statistical_stock_selection_differs_from_ross():
    ross_spec = StockSelectionSpec()
    stat_spec = statistical_stock_selection_spec()
    assert ross_spec.policy_name != stat_spec.policy_name
    assert ross_spec.gap_min_pct != stat_spec.gap_min_pct
    assert ross_spec.rvol_min != stat_spec.rvol_min
