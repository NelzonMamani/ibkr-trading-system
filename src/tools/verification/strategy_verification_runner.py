import importlib
from .verification_stage_library import run_all_stages
from .verification_evidence_writer import write_evidence_bundle

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
