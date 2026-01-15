"""Doctor bootstrap entrypoint for Epoch 5 readiness checks."""

from __future__ import annotations

from src.config.config_resolver import get_config
from src.core_engine.bootstrap import resolve_mode
from src.core_engine.state import resolve_session_state
from src.scanner.scanner_runner import run_scanner_cycle
from src.utils.logging import print_section, print_watchlist_focus


def run_doctor() -> int:
    mode = resolve_mode("READONLY")
    session = resolve_session_state()
    print_section("DOCTOR START")
    print(f"MODE={mode.value} SESSION={session.value}")

    try:
        import src  # noqa: F401
        print("[DOCTOR] Imports: OK")
    except Exception as exc:
        print(f"[DOCTOR] Imports: FAIL ({exc})")
        return 1

    try:
        get_config("RUN_MODE_EFFECTIVE")
        print("[DOCTOR] Config: OK")
    except Exception as exc:
        print(f"[DOCTOR] Config: FAIL ({exc})")
        return 1

    payload = run_scanner_cycle(mode=mode.value)
    watchlist = payload.get("watchlist_k", payload.get("watchlist", []))
    focus = payload.get("focus_m", [])
    drop_summary = payload.get("drop_reason_summary", {})
    print_section("SCANNER RESULT")
    print_watchlist_focus(watchlist, focus, drop_summary)
    print("[DOCTOR] Scanner cycle: OK")
    print_section("DOCTOR OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_doctor())
