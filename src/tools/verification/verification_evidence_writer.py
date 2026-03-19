import json
from datetime import datetime
from pathlib import Path
from typing import Any


def write_evidence_bundle(strategy_name, results):
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = Path("TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/strategy_verification") / strategy_name / timestamp
    path.mkdir(parents=True, exist_ok=True)
    with open(path / "results.json", "w") as f:
        json.dump(results, f, indent=2)
    return str(path)


def write_m5_v2_evidence(strategy_name: str, results: dict[str, Any]) -> str:
    base = Path("TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M5_STRATEGY_V2")
    path = base / strategy_name
    path.mkdir(parents=True, exist_ok=True)

    for stage, data in results["stages"].items():
        with open(path / f"{stage}.json", "w") as f:
            json.dump(data, f, indent=2)

    with open(path / "FINAL_CERTIFICATION.json", "w") as f:
        json.dump(results, f, indent=2)

    return str(path)
