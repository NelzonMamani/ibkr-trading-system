from pathlib import Path
import sys

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from src.config.config_resolver import set_config_overrides
from dataclasses import replace

from src.scanner import scanner_runner
from src.scanner.contracts import policy_from_config
from src.scanner.providers.mock_provider import MockScannerProvider


def _patch_low_rvol():
    orig_scanner_rvol = scanner_runner.compute_scanner_rvol
    orig_rel = scanner_runner.compute_session_relative_volume_with_provenance

    def low_scanner_rvol(*args, **kwargs):
        return 0.05

    def low_rel(*args, **kwargs):
        payload = orig_rel(*args, **kwargs)
        return replace(payload, value=0.05)

    scanner_runner.compute_scanner_rvol = low_scanner_rvol
    scanner_runner.compute_session_relative_volume_with_provenance = low_rel
    return orig_scanner_rvol, orig_rel


def main() -> int:
    set_config_overrides({"SCANNER_MODE": "TEACHING", "ROSS_REQUIRE_NEWS": False})
    policy = replace(policy_from_config(), watchlist_rvol_min=5.0, focus_rvol_min=5.0, watchlist_limit_k=4, focus_limit_m=2)
    provider = MockScannerProvider(symbols=["AAPL", "TSLA", "PLTR", "SOFI"])
    orig_scanner_rvol, orig_rel = _patch_low_rvol()
    try:
        after = scanner_runner.run_scanner_cycle(mode="LIVE", forced_session_label="AH", policy=policy, provider=provider, disconnect_provider=False)
        pre = scanner_runner.run_scanner_cycle(mode="LIVE", forced_session_label="PRE", policy=policy, provider=provider, disconnect_provider=False)
    finally:
        scanner_runner.compute_scanner_rvol = orig_scanner_rvol
        scanner_runner.compute_session_relative_volume_with_provenance = orig_rel
        set_config_overrides({})

    after_watch = after.get("watchlist_k_symbols", [])
    pre_watch = pre.get("watchlist_k_symbols", [])
    after_exec = [bool(getattr(c, "execution_ready", False)) for c in after.get("watchlist_k", [])]
    after_prep = [bool(getattr(c, "prep_only", False)) for c in after.get("watchlist_k", [])]

    print(f"after_watchlist_k={after_watch}")
    print(f"pre_watchlist_k={pre_watch}")
    print(f"after_execution_ready_flags={after_exec}")
    print(f"after_prep_only_flags={after_prep}")

    if not after_watch:
        print("FAIL: AFTER watchlist is empty; expected prep survival")
        return 1
    if pre_watch:
        print("FAIL: PRE watchlist not empty under low RVOL; expected strict live RVOL drops")
        return 1
    if any(after_exec):
        print("FAIL: AFTER prep symbol unexpectedly execution-ready")
        return 1
    if not all(after_prep):
        print("FAIL: AFTER prep symbol missing prep_only flag")
        return 1

    print("PASS: AFTER prep survives deferred RVOL; PRE remains strict; execution blocked in prep-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
