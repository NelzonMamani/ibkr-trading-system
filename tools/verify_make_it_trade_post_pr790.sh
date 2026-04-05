#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

REPORT_DIR="AUDIT_EVIDENCE/make_it_trade_post_pr790"
mkdir -p "$REPORT_DIR"

pytest -q tests/test_make_it_trade_pipeline_audit.py tests/test_trade_path_authority_model.py \
  | tee "$REPORT_DIR/pytest_trade_path_authority.txt"

pytest -q tests/test_p01_make_it_trade_layer.py tests/test_execution_pipeline_handoff_observability.py \
  | tee "$REPORT_DIR/pytest_pipeline_regression.txt"

python -m src.cli.test_trade_pipeline --symbol AAPL --dry-run \
  > "$REPORT_DIR/pipeline_validation_dry_run.log" 2>&1

python - <<'PY'
import json
from pathlib import Path

report_dir = Path("AUDIT_EVIDENCE/make_it_trade_post_pr790")
summary = {
    "pipeline_validation_log": str(report_dir / "pipeline_validation_dry_run.log"),
    "pytest_trade_path_authority": str(report_dir / "pytest_trade_path_authority.txt"),
    "pytest_pipeline_regression": str(report_dir / "pytest_pipeline_regression.txt"),
}
(report_dir / "verification_bundle.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
PY
