"""Doctor entrypoint for Epoch 5 bootstrap diagnostics."""
from __future__ import annotations

import sys

from src.config.system_config import get_current_market_session
from src.core_engine.bootstrap import apply_doctor_overrides, run_bootstrap_checks
from src.scanner.scanner_runner import print_cycle_summary, run_scanner_cycle
from src.utils.logging import print_mode_banner


def main() -> int:
    print("[DOCTOR] Starting bootstrap diagnostics")
    apply_doctor_overrides()

    session_label = get_current_market_session()
    print_mode_banner("READONLY", session_label)

    status = run_bootstrap_checks(
        modules=[
            "src.core.orchestrator",
            "src.scanner.scanner_runner",
            "src.config.config_resolver",
            "src.risk.risk_engine",
            "src.execution.execution_engine",
        ]
    )

    if status.imports_ok:
        print("[DOCTOR] Imports: OK")
    else:
        print("[DOCTOR] Imports: FAIL")
        for failure in status.import_failures:
            print(f"[DOCTOR] import_error={failure}")

    if status.config_ok:
        print("[DOCTOR] Config: OK")
    else:
        print("[DOCTOR] Config: FAIL")
        if status.config_error:
            print(f"[DOCTOR] config_error={status.config_error}")

    scanner_ok = True
    try:
        payload = run_scanner_cycle(mode="doctor")
        print_cycle_summary(payload)
        print("[DOCTOR] Scanner cycle: OK")
    except Exception as exc:
        scanner_ok = False
        print("[DOCTOR] Scanner cycle: FAIL")
        print(f"[DOCTOR] scanner_error={exc}")

    ok = status.imports_ok and status.config_ok and scanner_ok
    print(f"[DOCTOR] Summary: {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
