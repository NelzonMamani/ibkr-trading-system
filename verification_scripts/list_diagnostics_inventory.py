#!/usr/bin/env python3
"""
Usage:
  python verification_scripts/list_diagnostics_inventory.py

Purpose:
  Print a compact diagnostics/verification inventory for Ross readiness investigation.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TOOLS = [
    ("verification_scripts/verify_float_wiring.py", "Float data/cache authority verification", "float"),
    ("verification_scripts/verify_session_detection.py", "Session label resolution checks", "session"),
    ("verification_scripts/verify_ross_closed_prep_mode.py", "Closed/weekend prep proof", "prep"),
    ("verification_scripts/run_scanner_simulation.py", "Scanner/watchlist/focus simulation", "scanner"),
    ("verification_scripts/verify_policy_v2_resolver_runtime.py", "Policy resolver/runtime reconciliation", "policy"),
    ("verification_scripts/ross_live_execution_proof_pipeline.py", "Execution lifecycle proof pipeline", "execution"),
    ("verification_scripts/verify_ibkr_spot_check.py", "Broker connectivity smoke", "broker"),
]


if __name__ == "__main__":
    print("DIAGNOSTICS INVENTORY")
    for path, purpose, layer in TOOLS:
        exists = (REPO_ROOT / path).exists()
        print(f"- {path} | layer={layer} | exists={exists} | purpose={purpose}")
