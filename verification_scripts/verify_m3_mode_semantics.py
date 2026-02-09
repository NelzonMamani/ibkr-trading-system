from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


CANONICAL_MODES = ["SIM", "PAPER", "READ_ONLY", "LIVE"]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_enum_members(path: Path, class_name: str) -> List[str]:
    tree = ast.parse(_read_text(path))
    members: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                    target = stmt.targets[0]
                    if isinstance(target, ast.Name):
                        value_node = stmt.value
                        if isinstance(value_node, ast.Constant) and isinstance(
                            value_node.value, str
                        ):
                            members.append(value_node.value)
    return members


def _check_canonical_modes(repo_root: Path) -> Dict[str, Any]:
    state_modes = _extract_enum_members(
        repo_root / "src/core_engine/state.py", "RunMode"
    )
    runtime_modes = _extract_enum_members(
        repo_root / "src/config/runtime_config.py", "RunMode"
    )
    return {
        "core_engine_state": state_modes,
        "runtime_config": runtime_modes,
    }


def _check_config_registry(repo_root: Path) -> Dict[str, Any]:
    registry_text = _read_text(repo_root / "src/config/config_registry.py")
    run_mode_choices = re.search(
        r'"RUN_MODE"\s*:\s*{[^}]*"choices"\s*:\s*\[([^\]]+)\]',
        registry_text,
        re.MULTILINE | re.DOTALL,
    )
    effective_choices = re.search(
        r'"RUN_MODE_EFFECTIVE"\s*:\s*{[^}]*"choices"\s*:\s*\[([^\]]+)\]',
        registry_text,
        re.MULTILINE | re.DOTALL,
    )
    return {
        "run_mode_choices": run_mode_choices.group(1).replace("\n", "").strip()
        if run_mode_choices
        else None,
        "run_mode_effective_choices": effective_choices.group(1).replace("\n", "").strip()
        if effective_choices
        else None,
    }


def _check_read_only_guards(repo_root: Path) -> Dict[str, Any]:
    execution_text = _read_text(repo_root / "src/execution/execution_engine.py")
    router_text = _read_text(repo_root / "src/execution/order_router.py")
    return {
        "execution_engine_readonly_block": "RunMode.READ_ONLY" in execution_text
        and "LIVE_READ_ONLY_BLOCK" in execution_text,
        "order_router_readonly_block": "RunMode.READ_ONLY" in router_text
        and "WOULD_PLACE" in router_text,
    }


def _check_paper_provider(repo_root: Path) -> Dict[str, Any]:
    execution_text = _read_text(repo_root / "src/execution/execution_engine.py")
    return {
        "paper_provider_guard": "RunMode.PAPER" in execution_text
        and "PaperExecutionProvider" in execution_text,
    }


def _check_execution_enablement(repo_root: Path) -> Dict[str, Any]:
    resolver_text = _read_text(repo_root / "src/config/config_resolver.py")
    block_match = re.search(
        r'EXECUTION_ENABLED_EFFECTIVE[\s\S]{0,400}?value\s*=\s*(.+?)\n',
        resolver_text,
    )
    derived_expr = block_match.group(1).strip() if block_match else None
    block_text = block_match.group(0) if block_match else ""
    explicit_flags = [
        r"\bEXECUTION_ENABLED\b",
        r"\bIBKR_ORDER_SUBMISSION_ENABLED\b",
    ]
    uses_explicit_flag = any(re.search(flag, block_text) for flag in explicit_flags)
    return {
        "execution_enabled_effective_expr": derived_expr,
        "uses_explicit_flag": uses_explicit_flag,
    }


def _check_sim_broker_isolation(repo_root: Path) -> Dict[str, Any]:
    connection_text = _read_text(
        repo_root / "src/core/managers/connection_manager.py"
    )
    market_data_text = _read_text(repo_root / "src/market_data/market_data_hub.py")
    sim_mentions = "RunMode.SIM" in connection_text or "RunMode.SIM" in market_data_text
    sim_mock_guard = "SIM mode with MOCK scanner; skipping IBKR connect." in connection_text
    sim_guard_depends_on_mock = (
        "RunMode.SIM" in connection_text and "SCANNER_DATA_SOURCE" in connection_text
    )
    return {
        "sim_mentions": sim_mentions,
        "sim_mock_guard": sim_mock_guard,
        "sim_guard_depends_on_mock": sim_guard_depends_on_mock,
    }


def evaluate_mode_semantics(repo_root: Path) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "canonical_modes": CANONICAL_MODES,
        "checks": {},
        "violations": [],
        "notes": [],
    }

    mode_checks = _check_canonical_modes(repo_root)
    results["checks"]["run_mode_enums"] = mode_checks
    for location, modes in mode_checks.items():
        if sorted(modes) != sorted(CANONICAL_MODES):
            results["violations"].append(
                f"RunMode enum mismatch in {location}: {modes}"
            )

    registry_checks = _check_config_registry(repo_root)
    results["checks"]["config_registry"] = registry_checks
    for key, value in registry_checks.items():
        if value is None:
            results["violations"].append(f"Missing {key} in config_registry choices.")
        elif not all(mode in value for mode in CANONICAL_MODES):
            results["violations"].append(
                f"Config registry {key} does not enumerate all canonical modes: {value}"
            )

    readonly_checks = _check_read_only_guards(repo_root)
    results["checks"]["read_only_guards"] = readonly_checks
    if not readonly_checks["execution_engine_readonly_block"]:
        results["violations"].append("Execution engine lacks READ_ONLY guard.")
    if not readonly_checks["order_router_readonly_block"]:
        results["violations"].append("Order router lacks READ_ONLY guard.")

    paper_checks = _check_paper_provider(repo_root)
    results["checks"]["paper_provider"] = paper_checks
    if not paper_checks["paper_provider_guard"]:
        results["violations"].append("PAPER mode does not enforce paper provider.")

    execution_checks = _check_execution_enablement(repo_root)
    results["checks"]["execution_enablement"] = execution_checks
    if not execution_checks["uses_explicit_flag"]:
        results["violations"].append(
            "LIVE execution enablement is derived only from run mode; "
            "explicit enablement flag not enforced."
        )

    sim_checks = _check_sim_broker_isolation(repo_root)
    results["checks"]["sim_broker_isolation"] = sim_checks
    if sim_checks["sim_guard_depends_on_mock"]:
        results["violations"].append(
            "SIM broker isolation is conditional on MOCK data source; "
            "no hard block prevents live broker connections."
        )
    if sim_checks["sim_mentions"] and not sim_checks["sim_mock_guard"]:
        results["violations"].append(
            "SIM broker isolation lacks a hard block; live broker connections may occur."
        )
    if not sim_checks["sim_mentions"]:
        results["violations"].append(
            "No SIM-specific broker isolation logic detected in connection managers."
        )

    results["status"] = "PASS" if not results["violations"] else "FAIL"
    return results


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    results = evaluate_mode_semantics(repo_root)
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if results["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
