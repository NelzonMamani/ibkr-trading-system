# FILE: verification_scripts/verify_all.py
# TITLE: Single-entry Verification Runner (path-based imports; no package required)

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any
import importlib.util

HERE = Path(__file__).resolve().parent

def _load_sibling(module_filename: str):
    """
    Load a module from a sibling .py file inside verification_scripts/, without package imports.
    """
    path = HERE / module_filename
    if not path.exists():
        raise FileNotFoundError(f"Missing verification module file: {path}")

    module_name = f"_verify_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {path}")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod

def _run(filename: str, func: str, **kwargs) -> Dict[str, Any]:
    mod = _load_sibling(filename)
    fn = getattr(mod, func)
    return fn(**kwargs)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="LIVE_READ_ONLY", help="SIM | PAPER | LIVE_READ_ONLY | LIVE_MICRO | LIVE")
    ap.add_argument("--strategy", default="ross_momentum", help="strategy key/name used by your system")
    ap.add_argument("--db", default=str(Path("data") / "ibkr_system.db"), help="SQLite path")
    ap.add_argument("--ibkr", action="store_true", help="attempt IBKR spot-checks (requires TWS/IBG running)")
    ap.add_argument("--json", action="store_true", help="print JSON report at end")
    args = ap.parse_args()

    report: Dict[str, Any] = {"mode": args.mode, "strategy": args.strategy, "checks": {}}

    report["checks"]["runtime_wiring"] = _run("verify_runtime_wiring.py", "verify_runtime_wiring", mode=args.mode)
    report["checks"]["strategy_wiring"] = _run("verify_strategy_wiring.py", "verify_strategy_wiring")
    report["checks"]["session_detection"] = _run("verify_session_detection.py", "verify_session_detection")
    report["checks"]["db_readiness"] = _run("verify_db_readiness.py", "verify_db_readiness", db_path=args.db)
    report["checks"]["focus_injection"] = _run("verify_focus_injection.py", "verify_focus_injection")

    if args.ibkr:
        report["checks"]["ibkr_spot_check"] = _run("verify_ibkr_spot_check.py", "verify_ibkr_spot_check")

    print("\n=== VERIFICATION SUMMARY ===")
    hard_fail = False
    for k, v in report["checks"].items():
        status = v.get("status", "UNKNOWN")
        print(f"- {k}: {status}")
        if status in ("FAIL", "ERROR"):
            hard_fail = True

    if args.json:
        print("\n=== JSON REPORT ===")
        print(json.dumps(report, indent=2, default=str))

    return 1 if hard_fail else 0

if __name__ == "__main__":
    raise SystemExit(main())
# END
