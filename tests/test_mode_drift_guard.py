from __future__ import annotations

import pytest

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator, RuntimeSafetyError


def test_runtime_mode_drift_triggers_safety_violation():
    set_config_overrides({"RUN_MODE": "SIM"})
    try:
        orchestrator = CoreOrchestrator()
        set_config_overrides({"RUN_MODE": "PAPER"})
        with pytest.raises(RuntimeSafetyError, match="Run mode drift"):
            orchestrator._evaluate_runtime_safety(cycle_stage="CYCLE_START")
    finally:
        set_config_overrides({})
