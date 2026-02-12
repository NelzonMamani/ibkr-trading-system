"""Verifier for E22 strategy scalability and arbitration layer."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.e22.strategy_scalability_and_arbitration import E22PolicyConfig, IntentArbitrator
from src.metadata.m0_canon_helpers import update_system_state_statuses
from src.models.data_models import TradeIntent

EPOCH = "E22_STRATEGY_SCALABILITY_AND_ARBITRATION_LAYER"
EVIDENCE_DIR_REL = Path("TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE") / EPOCH
STATE_FILE_REL = Path("TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md")


def _normalize_output(command: list[str], text: str) -> str:
    if "pytest" in command:
        text = re.sub(r"in\s+\d+\.\d+s", "in <DURATION>", text)
        text = re.sub(r"\(0:0\d:0\d\)", "(<ELAPSED>)", text)
    return text


def _run_to_file(command: list[str], output_path: Path) -> int:
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    stdout = _normalize_output(command, completed.stdout)
    stderr = _normalize_output(command, completed.stderr)
    output_path.write_text((f"$ {' '.join(command)}\n\n{stdout}\n{stderr}").strip() + "\n", encoding="utf-8")
    return completed.returncode


def _stable_payload(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k not in {"generated_at_utc"}}


def _fixture_intent(strategy: str, symbol: str, confidence: float) -> TradeIntent:
    return TradeIntent(
        symbol=symbol,
        direction="LONG",
        strategy_name=strategy,
        confidence=confidence,
        rationale="e22 verifier fixture",
        trader_type="QUANT",
    )


def _determinism_check() -> tuple[bool, dict]:
    intents = [
        _fixture_intent("alpha", "ABC", 0.9),
        _fixture_intent("beta", "ABC", 0.8),
        _fixture_intent("alpha", "XYZ", 0.7),
        _fixture_intent("gamma", "QQQ", 0.6),
    ]
    config = E22PolicyConfig(
        enabled=True,
        max_strategies_per_cycle=2,
        max_intents_per_cycle=2,
        max_positions_per_cycle=2,
        symbol_exclusivity=True,
        strategy_priority={"alpha": 10, "beta": 5, "gamma": 1},
        strategy_max_intents={"alpha": 2, "beta": 1, "gamma": 1},
    )
    a = IntentArbitrator().arbitrate(intents, config)
    b = IntentArbitrator().arbitrate(intents, config)
    payload_a = {
        "allowed": [[i.strategy_name, i.symbol, i.direction] for i in a.allowed_intents],
        "suppressed": [
            [i.strategy_name, i.symbol, i.direction, i.reason_code, list(sorted(i.context.items()))]
            for i in a.suppressed_intents
        ],
        "counts": a.suppression_counts_by_reason_code,
        "strategy_order": a.strategy_order,
    }
    payload_b = {
        "allowed": [[i.strategy_name, i.symbol, i.direction] for i in b.allowed_intents],
        "suppressed": [
            [i.strategy_name, i.symbol, i.direction, i.reason_code, list(sorted(i.context.items()))]
            for i in b.suppressed_intents
        ],
        "counts": b.suppression_counts_by_reason_code,
        "strategy_order": b.strategy_order,
    }
    return payload_a == payload_b, payload_a


def _build_evidence_index(evidence_dir: Path) -> dict:
    files = []
    for path in sorted(evidence_dir.glob("*")):
        if path.is_file():
            files.append({"file": path.name, "bytes": path.stat().st_size})
    return {"epoch": EPOCH, "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "files": files}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify E22 strategy scalability and arbitration layer")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()

    evidence_dir = REPO_ROOT / EVIDENCE_DIR_REL
    required = {
        "compileall.txt",
        "pytest_full.txt",
        "verification_summary.md",
        "verification_output.json",
        "e22_verifier_output.json",
        "EVIDENCE_INDEX.json",
        "certification_verdict.json",
    }

    if evidence_dir.exists() and args.allow_overwrite:
        shutil.rmtree(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    if not args.allow_overwrite and any((evidence_dir / name).exists() for name in required):
        print("Refusing overwrite without --allow-overwrite")
        return 2

    compile_rc = _run_to_file([sys.executable, "-m", "compileall", "-q", "src", "tests", "verification_scripts"], evidence_dir / "compileall.txt")
    pytest_rc = _run_to_file([sys.executable, "-m", "pytest", "-q"], evidence_dir / "pytest_full.txt")

    deterministic, deterministic_payload = _determinism_check()

    output = {
        "epoch": EPOCH,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "valid": compile_rc == 0 and pytest_rc == 0 and deterministic,
        "violations": [],
        "metrics": {
            "strategies_enabled_count": 3,
            "strategies_executed_count": len(deterministic_payload["strategy_order"]),
            "arbitration_intents_total": 4,
            "arbitration_intents_allowed": len(deterministic_payload["allowed"]),
            "arbitration_intents_suppressed": len(deterministic_payload["suppressed"]),
            "suppression_counts_by_reason_code": deterministic_payload["counts"],
            "budgets_consumed_per_strategy": {
                name: sum(1 for item in deterministic_payload["allowed"] if item[0] == name)
                for name in sorted(set(deterministic_payload["strategy_order"]))
            },
            "latency_stage_ms": {"scheduler": 0, "coordinator": 0, "arbitrator": 0},
        },
        "determinism": {"stable": deterministic, "sample": deterministic_payload},
    }
    if not deterministic:
        output["violations"].append(
            {
                "check": "E22_DETERMINISTIC_ARBITRATION",
                "expected": "stable_outputs",
                "actual": "non_deterministic",
            }
        )

    (evidence_dir / "verification_output.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (evidence_dir / "e22_verifier_output.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    certified = output["valid"]
    verdict = {
        "epoch": EPOCH,
        "verdict": "CERTIFIED" if certified else "NOT_CERTIFIED",
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reasons": [] if certified else ["verification_failed"],
        "evidence": sorted(required),
    }
    (evidence_dir / "certification_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary_lines = [
        "# E22 Verification Summary",
        "",
        f"- compileall_exit_code: `{compile_rc}`",
        f"- pytest_exit_code: `{pytest_rc}`",
        f"- determinism_ok: `{deterministic}`",
        f"- verdict: `{'CERTIFIED' if certified else 'NOT_CERTIFIED'}`",
        "",
        "## Evidence",
    ]
    for name in sorted(required):
        summary_lines.append(f"- `{name}`")
    (evidence_dir / "verification_summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    (evidence_dir / "EVIDENCE_INDEX.json").write_text(
        json.dumps(_build_evidence_index(evidence_dir), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if certified:
        update_system_state_statuses(REPO_ROOT / STATE_FILE_REL, {"E22_STRATEGY_SCALABILITY_AND_ARBITRATION_LAYER": "CERTIFIED"})

    return 0 if certified else 1


if __name__ == "__main__":
    raise SystemExit(main())
