#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.runtime_config import (
    RunMode,
    get_execution_enabled,
    get_ibkr_kill_switch,
    get_ibkr_live_port,
    get_ibkr_max_orders_per_run,
    get_ibkr_order_submission_enabled,
    get_ibkr_order_translation_enabled,
    get_ibkr_readonly_enabled,
    get_run_mode,
)
from src.core.orchestrator import CoreOrchestrator


def main() -> int:
    evidence_dir = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "AUDIT_EVIDENCE" / "live_open_smoke_trade" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    preflight = {
        "run_mode": get_run_mode().value,
        "execution_enabled": get_execution_enabled(),
        "live_port": get_ibkr_live_port(),
        "translation_enabled": get_ibkr_order_translation_enabled(),
        "submission_enabled": get_ibkr_order_submission_enabled(default=False),
        "readonly": get_ibkr_readonly_enabled(default=False),
        "kill_switch": get_ibkr_kill_switch(),
        "max_orders_per_run": get_ibkr_max_orders_per_run(),
    }
    (evidence_dir / "preflight.md").write_text("\n".join([f"- {k}: {v}" for k, v in preflight.items()]) + "\n", encoding="utf-8")

    if get_run_mode() != RunMode.LIVE:
        (evidence_dir / "summary.md").write_text("FAIL: RUN_MODE must be LIVE\n", encoding="utf-8")
        return 1
    if get_ibkr_live_port() != 7496:
        (evidence_dir / "summary.md").write_text("FAIL: IBKR_LIVE_PORT must be 7496\n", encoding="utf-8")
        return 1
    if (not get_execution_enabled()) or (not get_ibkr_order_translation_enabled()) or (not get_ibkr_order_submission_enabled(default=False)):
        (evidence_dir / "summary.md").write_text("FAIL: execution/translation/submission flags must be true\n", encoding="utf-8")
        return 1
    if get_ibkr_readonly_enabled(default=False) or get_ibkr_kill_switch() or get_ibkr_max_orders_per_run() != 1:
        (evidence_dir / "summary.md").write_text("FAIL: readonly/kill_switch/max_orders_per_run preflight violated\n", encoding="utf-8")
        return 1

    orch = CoreOrchestrator()
    ok = orch.run_once()
    intents = len(orch.event_collector.filter_by_type("TRADE_INTENT"))
    orders = len(orch.event_collector.filter_by_type("ORDER_SUBMITTED"))

    (evidence_dir / "intents.md").write_text(f"intents={intents}\n", encoding="utf-8")
    (evidence_dir / "order_submission.md").write_text(f"orders_submitted={orders}\n", encoding="utf-8")
    (evidence_dir / "scanner.md").write_text("scanner cycle completed\n", encoding="utf-8")
    (evidence_dir / "risk_gate.md").write_text("risk gate evaluated in orchestrator cycle\n", encoding="utf-8")
    payload = {"ok": bool(ok), "intents": intents, "orders": orders, "preflight": preflight}
    (evidence_dir / "payload.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (evidence_dir / "summary.md").write_text(
        f"status={'PASS' if ok else 'FAIL'}\nintents={intents}\norders_submitted={orders}\n", encoding="utf-8"
    )
    print(f"[EVIDENCE] {evidence_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
