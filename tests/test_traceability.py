import json
import time

import pytest

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.core.stop_controller import StopMode
from src.execution.startup_recovery_authority import RecoveryState, StartupRecoveryResult
from src.scanner.providers.base import ProviderConnectionError
from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec
from src.strategies.statistical_intraday_momentum.strategy_policy import (
    statistical_stock_selection_spec,
)


def _reset_overrides():
    set_config_overrides(None)


def _halt_metadata(record: dict) -> dict:
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    return record


def _stub_startup_recovery_complete(orchestrator: CoreOrchestrator) -> None:
    orchestrator.execution_engine.startup_recovery_state = RecoveryState.RECOVERY_COMPLETE
    orchestrator.execution_engine.startup_recovery_result = StartupRecoveryResult(
        state=RecoveryState.RECOVERY_COMPLETE,
        reason="TEST_RECOVERY_COMPLETE",
    )
    orchestrator.execution_engine._failsafe_block_new_entries = False


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
    _stub_startup_recovery_complete(orchestrator)
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
    halt_record = None
    for candidate in halt_lines:
        metadata = _halt_metadata(candidate)
        if metadata.get("reason_code") == "CONNECTIVITY_FAILURE":
            halt_record = metadata
            break
    assert halt_record is not None
    assert halt_record["stage"] == "HALT"
    assert halt_record["halt_stage"] == "CONNECTIVITY"
    assert halt_record["reason_code"] == "CONNECTIVITY_FAILURE"
    assert halt_record["message"]
    assert halt_record["details"] == {} or isinstance(halt_record["details"], dict)

    stop_complete_index = None
    halt_index = None
    for index, line in enumerate(log_files[0].read_text(encoding="utf-8").splitlines()):
        record = json.loads(line)
        if record.get("stage") == "HALT" and halt_index is None:
            halt_index = index
        if record.get("stage") == "STOP_COMPLETE" and stop_complete_index is None:
            stop_complete_index = index
    assert halt_index is not None
    if stop_complete_index is not None:
        assert halt_index < stop_complete_index


def test_connectivity_halt_not_suppressed_by_prior_halt(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_LOG_DIR", str(tmp_path))
    set_config_overrides({"RUN_MODE": "READ_ONLY", "IBKR_FALLBACK_ENABLED": False})

    orchestrator = CoreOrchestrator()
    orchestrator._emit_canonical_halt(
        reason_code="PREVIOUS_HALT",
        message="older halt should not suppress connectivity halt",
        halt_stage="RISK",
    )

    def fake_run_once():
        raise ProviderConnectionError("IBKR down")

    monkeypatch.setattr(orchestrator, "run_once", fake_run_once)

    def fake_sleep(_seconds):
        orchestrator.stop_controller.request_stop(
            StopMode.GRACEFUL, reason="test", source="test"
        )

    monkeypatch.setattr(time, "sleep", fake_sleep)

    orchestrator.run_forever(max_cycles=None, cycle_sleep_seconds=0)

    log_files = list(tmp_path.glob("trace_*.jsonl"))
    assert log_files, "trace log file missing"

    halt_reason_codes = []
    for line in log_files[0].read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("stage") != "HALT":
            continue
        metadata = _halt_metadata(record)
        halt_reason_codes.append(metadata.get("reason_code"))

    assert "PREVIOUS_HALT" in halt_reason_codes
    assert "CONNECTIVITY_FAILURE" in halt_reason_codes

def test_canonical_halt_schema_and_origin_are_stable(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_LOG_DIR", str(tmp_path))
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "SELECTED_STRATEGY": "ross_momentum",
        }
    )

    orchestrator = CoreOrchestrator()
    orchestrator._emit_canonical_halt(
        reason_code="UNIT_TEST",
        message="halt schema check",
        halt_stage="CONNECTIVITY",
        details={"stage": "SHOULD_NOT_OVERWRITE", "origin": "unit-test"},
    )

    log_files = list(tmp_path.glob("trace_*.jsonl"))
    assert log_files, "trace log file missing"

    halt_record = None
    for line in log_files[0].read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("stage") == "HALT":
            halt_record = record

    assert halt_record is not None
    halt_record = _halt_metadata(halt_record)
    assert halt_record["stage"] == "HALT"
    assert halt_record["halt_stage"] == "CONNECTIVITY"
    assert halt_record["reason_code"] == "UNIT_TEST"
    assert halt_record["message"] == "halt schema check"
    assert halt_record["details"] == {
        "stage": "SHOULD_NOT_OVERWRITE",
        "origin": "unit-test",
    }


def test_statistical_stock_selection_differs_from_ross():
    ross_spec = StockSelectionSpec()
    stat_spec = statistical_stock_selection_spec()
    assert ross_spec.policy_name != stat_spec.policy_name
    assert ross_spec.gap_min_pct != stat_spec.gap_min_pct
    assert ross_spec.rvol_min != stat_spec.rvol_min
