#!/usr/bin/env python3
"""
Usage:
  python verification_scripts/verify_ross_closed_prep_mode.py

Purpose:
  Verify Ross CLOSED/weekend preparation semantics and session-aware reference logic.

Outputs:
  - JSON evidence under AUDIT_EVIDENCE/ross_session_hardening/
  - PASS/FAIL summary in stdout
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.scanner.session_pct_change import (
    compute_session_aligned_pct_change,
    compute_session_relative_volume_with_provenance,
    resolve_session_diagnostics,
)

OUT_DIR = REPO_ROOT / "AUDIT_EVIDENCE" / "ross_session_hardening"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    weekend_probe = datetime(2026, 1, 24, 15, 0, tzinfo=timezone.utc)  # Saturday
    diagnostics = resolve_session_diagnostics(weekend_probe)

    pct_payload = compute_session_aligned_pct_change(
        session_label="WEEKEND",
        cur_last=11.0,
        ref_close_rth=10.0,
        rth_open_price=10.2,
        rth_close_price=10.0,
        ibkr_change_pct=None,
        persisted_pct_change=9.9,
    )
    rvol_payload = compute_session_relative_volume_with_provenance(
        session_label="WEEKEND",
        session_volume=120000,
        avg_volume_20d=5000000,
        persisted_rvol=2.4,
        symbol="TEST",
    )

    payload = {
        "probe_utc": weekend_probe.isoformat(),
        "session_diagnostics": diagnostics.__dict__,
        "pct_payload": pct_payload.__dict__,
        "rvol_payload": rvol_payload.__dict__,
        "assertions": {
            "resolved_closed": diagnostics.canonical_session == "CLOSED",
            "previous_valid_market_session_date_present": bool(diagnostics.previous_valid_market_session_date),
            "weekend_pct_uses_persisted_reference": pct_payload.pct_source == "PERSISTED_LAST_SESSION",
            "weekend_rvol_context_available": rvol_payload.value == 0.0,
        },
    }
    payload["pass"] = all(payload["assertions"].values())

    out_path = OUT_DIR / "closed_prep_verification_report.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[REPORT] {out_path}")
    print("PASS" if payload["pass"] else "FAIL")
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
