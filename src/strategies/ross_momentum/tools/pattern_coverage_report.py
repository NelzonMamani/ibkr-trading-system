"""Pattern coverage report for Ross Momentum completeness checks."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry


REQUIRED_PATTERNS = [
    "Gap & Go",
    "Opening Range Breakout",
    "First Pullback",
    "Micro Pullback",
    "Bull Flag",
    "High Tight Flag",
    "Break of Key Level",
    "ABCD Continuation",
    "Cup & Handle",
    "Momentum Reclaim",
    "Flat-Top / Ascending Breakout",
    "Red-to-Green",
    "Green-to-Red",
    "Half-Dollar Break",
    "Whole-Dollar Break",
    "Premarket High Break",
    "Halt Resume Continuation",
    "Parabolic Exhaustion",
]


def _slug(name: str) -> str:
    cleaned = (
        name.lower()
        .replace("&", "and")
        .replace("/", " ")
        .replace("-", " ")
    )
    parts = [part for part in cleaned.split() if part]
    return "_".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ross pattern coverage report")
    parser.add_argument("--tests-dir", default="tests")
    args = parser.parse_args()

    registry = RossPatternRegistry()
    registered = {pattern.name for pattern in registry.patterns}

    missing = [name for name in REQUIRED_PATTERNS if name not in registered]
    missing_tests = []
    tests_dir = Path(args.tests_dir)
    for name in REQUIRED_PATTERNS:
        slug = _slug(name)
        test_file = tests_dir / f"test_ross_pattern_{slug}.py"
        if not test_file.exists():
            missing_tests.append(test_file.as_posix())

    if missing or missing_tests:
        print("[PATTERN_COVERAGE] FAIL")
        if missing:
            print("[PATTERN_COVERAGE] Missing detectors:", ", ".join(missing))
        if missing_tests:
            print("[PATTERN_COVERAGE] Missing tests:", ", ".join(missing_tests))
        return 1

    print("[PATTERN_COVERAGE] PASS")
    print(f"[PATTERN_COVERAGE] Detectors={len(registered)} tests={len(REQUIRED_PATTERNS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
