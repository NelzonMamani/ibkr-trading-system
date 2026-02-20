from __future__ import annotations

import json
from datetime import datetime, timezone
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = REPO_ROOT / "AUDIT_EVIDENCE" / "E26_regenerability_report.json"
MATRIX_PATH = REPO_ROOT / "AUDIT_EVIDENCE" / "E26_runtime_classification_matrix.json"


def _run(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True)
    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def main() -> int:
    runtime_roots = [REPO_ROOT / "data", REPO_ROOT / "logs", REPO_ROOT / "output"]
    before = {str(path.relative_to(REPO_ROOT)): path.exists() for path in runtime_roots}

    for path in runtime_roots:
        if path.exists():
            shutil.rmtree(path)

    commands = [
        ["python", "-m", "compileall", "src"],
        ["pytest", "-q"],
        ["python", "-m", "src.runtime.regen", "snapshot-registry"],
        ["python", "-m", "src.runtime.regen", "bootstrap"],
        ["python", "-m", "src.core_engine.orchestrator", "--mode", "READ_ONLY", "--cycles", "1"],
    ]
    results = [_run(cmd) for cmd in commands]

    after = {str(path.relative_to(REPO_ROOT)): path.exists() for path in runtime_roots}

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "commands": results,
        "runtime_before": before,
        "runtime_after": after,
        "all_commands_passed": all(result["exit_code"] == 0 for result in results),
    }

    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    matrix = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "categories": [
            {"category": "CANONICAL", "examples": ["src/", "tests/", "TRADING_OS_MASTER_CATALOGUE/"]},
            {"category": "REGENERABLE", "examples": ["data/*.db", "logs/", "output/"]},
            {"category": "SEMI_PERSISTENT", "examples": ["data/backups/", "analytical snapshots"]},
        ],
    }
    MATRIX_PATH.write_text(json.dumps(matrix, indent=2, sort_keys=True), encoding="utf-8")

    return 0 if report["all_commands_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
