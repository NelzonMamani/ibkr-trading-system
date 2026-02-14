"""Verification script for M5 verification authority."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m5_verification_authority_verifier import (
    verify_m5_verification_authority,
    write_outputs,
)
from src.metadata.m5_strategy_certification_authority import (
    generate_strategy_certification_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M5 verification authority")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    generate_strategy_certification_artifacts()
    result = verify_m5_verification_authority()
    evidence_index_json = args.output_json.parent / "M5_EVIDENCE_INDEX.json"
    write_outputs(result, args.output_json, args.output_md, evidence_index_json)

    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
