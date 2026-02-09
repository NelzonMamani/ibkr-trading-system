"""Verification script for M2 contract registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m0_canon_helpers import write_json
from src.metadata.m2_contract_verifier import verify_registry, write_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M2 contract registry")
    parser.add_argument("--registry-path", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    result = verify_registry(args.registry_path)
    write_json(args.output_json, result)
    write_summary(result, args.output_md)

    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
