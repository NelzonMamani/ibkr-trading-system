import json
from pathlib import Path
from datetime import datetime

def write_evidence_bundle(strategy_name, results):
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = Path("TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/strategy_verification") / strategy_name / timestamp
    path.mkdir(parents=True, exist_ok=True)
    with open(path / "results.json", "w") as f:
        json.dump(results, f, indent=2)
    return str(path)
