#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator


def main() -> int:
    set_config_overrides(None)
    orch = CoreOrchestrator()
    stream = io.StringIO()
    with redirect_stdout(stream):
        ok = orch.run_once()
    output = stream.getvalue()
    print(output)

    required = [
        "[ORCH][SCANNER_REQUEST] strategy=ross_momentum",
        "[ORCH][SCANNER_REQUEST] strategy=statistical_intraday_momentum",
        "[ORCH][SCANNER_REQUEST] strategy=mean_reversion",
    ]
    missing = [entry for entry in required if entry not in output]
    evidence_dir = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / "multi_strategy_orch_smoke" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": bool(ok),
        "missing": missing,
        "provider": type(getattr(orch.execution_engine, "provider", None)).__name__,
    }
    (evidence_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if missing:
        print(f"[FAIL] Missing scanner requests: {missing}")
        return 1
    print("[PASS] Multi-strategy scanner requests observed.")
    print(f"[EVIDENCE] {evidence_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
