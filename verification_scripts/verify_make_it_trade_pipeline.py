from __future__ import annotations

import json
from pathlib import Path
import sys

BASE = Path("AUDIT_EVIDENCE/make_it_trade_guarantee")


def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    summary = _load_json(BASE / "pipeline_summary.json")
    outcomes = _load_json(BASE / "kept_symbol_terminal_outcomes.json") or {}
    violations = _load_json(BASE / "contract_violations.json") or []

    if summary is None:
        print("[VERIFY][FAIL] Missing AUDIT_EVIDENCE/make_it_trade_guarantee/pipeline_summary.json")
        return 1

    kept = [str(s).upper() for s in summary.get("kept_symbols", [])]
    print("symbol | kept | focus | evaluated | pattern_detected | decision | trigger | trade_intent | execution | terminal_outcome")
    print("-" * 120)
    missing = []
    for symbol in kept:
        record = outcomes.get(symbol)
        if not record:
            missing.append(symbol)
            print(f"{symbol} | Y | ? | ? | ? | ? | ? | ? | ? | MISSING")
            continue
        outcome = str(record.get("outcome", ""))
        focus = "Y" if outcome != "NOT_IN_FOCUS" else "N"
        evaluated = "Y" if focus == "Y" else "N"
        pattern_detected = "Y" if outcome in {"TRADE_INTENT_CREATED", "RISK_BLOCKED", "EXECUTION_BLOCKED", "EXECUTION_SUBMITTED", "DECISION_REJECTED", "TRIGGER_NOT_FIRED"} else "N"
        decision = "ALLOW" if outcome in {"TRADE_INTENT_CREATED", "RISK_BLOCKED", "EXECUTION_BLOCKED", "EXECUTION_SUBMITTED", "TRIGGER_NOT_FIRED"} else "REJECT"
        trigger = "PASS" if outcome in {"TRADE_INTENT_CREATED", "RISK_BLOCKED", "EXECUTION_BLOCKED", "EXECUTION_SUBMITTED"} else "REJECT"
        trade_intent = "Y" if outcome in {"TRADE_INTENT_CREATED", "RISK_BLOCKED", "EXECUTION_BLOCKED", "EXECUTION_SUBMITTED"} else "N"
        execution = "SUBMITTED" if outcome == "EXECUTION_SUBMITTED" else ("BLOCKED" if outcome in {"EXECUTION_BLOCKED", "RISK_BLOCKED"} else "N/A")
        print(f"{symbol} | Y | {focus} | {evaluated} | {pattern_detected} | {decision} | {trigger} | {trade_intent} | {execution} | {outcome}")

    if violations:
        print(f"[VERIFY][FAIL] Contract violations present count={len(violations)}")
        for item in violations:
            print(f" - symbol={item.get('symbol')} reason={item.get('reason')} last_stage={item.get('last_stage')}")
        return 1
    if missing:
        print(f"[VERIFY][FAIL] Missing terminal outcomes for symbols={missing}")
        return 1

    print(f"[VERIFY][PASS] kept_symbols={len(kept)} all_accounted_for=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
