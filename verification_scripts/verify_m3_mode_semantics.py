"""Verification script for M3 mode semantics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.metadata.m3_mode_semantics_verifier import verify_mode_semantics, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M3 mode semantics")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    result = verify_mode_semantics()
    write_outputs(result, args.output_json, args.output_md)

    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
