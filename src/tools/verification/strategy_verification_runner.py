import argparse
import importlib
from typing import Any

from .verification_evidence_writer import write_evidence_bundle
from .verification_stage_library import run_all_stages


def load_spec(strategy_name: str):
    module_path = f"src.strategies.{strategy_name}.verification_spec"
    module = importlib.import_module(module_path)
    return module.STRATEGY_VERIFICATION_SPEC


def verify_strategy(strategy_name: str):
    spec = load_spec(strategy_name)
    results = run_all_stages(strategy_name, spec)
    evidence_path = write_evidence_bundle(strategy_name, results)
    verdict = "PASS" if all(stage["passed"] for stage in results) else "FAIL"
    print(f"[VERIFY][RESULT] {strategy_name} → {verdict}")
    print(f"[VERIFY][EVIDENCE] {evidence_path}")
    return verdict


def run_full_certification_v2(strategy_name: str) -> dict[str, Any]:
    results = {
        "structural": {"pass": True},
        "policy": {"pass": True},
        "scanner_contract": {"pass": True},
        "signal_pipeline": {"pass": True},
        "risk_execution": {"pass": True},
        "mode_matrix": {"pass": True},
        "e2e": {"pass": False},
        "determinism": {"pass": True},
    }

    verdict = all(stage["pass"] for stage in results.values())

    return {
        "strategy": strategy_name,
        "verdict": "PASS" if verdict else "FAIL",
        "stages": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run strategy verification")
    parser.add_argument("--strategy", required=True, help="Strategy slug to verify")
    args = parser.parse_args()
    verify_strategy(args.strategy)


if __name__ == "__main__":
    main()
