from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.metadata.m0_canon_helpers import get_repo_root, sha256_for_file, write_json
from src.metadata.m2_contract_registry import (
    ALLOWED_MODES,
    ALLOWED_OWNER_COMPONENTS,
    find_duplicate_ids,
    load_registry,
    validate_registry,
)


@dataclass(frozen=True)
class PathCheck:
    contract_id: str
    path: str
    exists: bool


def _iter_contract_paths(contracts: Iterable[dict]) -> Iterable[tuple[str, str, str]]:
    for contract in contracts:
        contract_id = str(contract.get("id"))
        status = str(contract.get("status"))
        for path in contract.get("paths", []) if isinstance(contract.get("paths"), list) else []:
            if isinstance(path, str):
                yield contract_id, status, path


def _path_exists(repo_root: Path, rel_path: str) -> bool:
    return (repo_root / rel_path).exists()


def verify_registry(registry_path: Path | None = None) -> dict:
    repo_root = get_repo_root(Path(__file__).resolve())
    registry = load_registry(registry_path)
    schema_errors = validate_registry(registry)
    contracts = registry.get("contracts", []) if isinstance(registry.get("contracts"), list) else []
    duplicate_ids = find_duplicate_ids(contracts)

    missing_paths: list[dict] = []
    declared_path_violations: list[dict] = []
    for contract_id, status, rel_path in _iter_contract_paths(contracts):
        if status == "declared":
            if not rel_path.startswith("TRADING_OS_MASTER_CATALOGUE"):
                declared_path_violations.append(
                    {"id": contract_id, "path": rel_path, "reason": "declared_outside_catalogue"}
                )
            continue
        if not _path_exists(repo_root, rel_path):
            missing_paths.append({"id": contract_id, "path": rel_path})

    invalid_owners = [
        contract.get("id")
        for contract in contracts
        if contract.get("owner_component") not in ALLOWED_OWNER_COMPONENTS
    ]
    invalid_modes = [
        contract.get("id")
        for contract in contracts
        if not set(contract.get("applies_to_modes", [])).issubset(ALLOWED_MODES)
    ]

    valid = not (schema_errors or duplicate_ids or missing_paths or declared_path_violations)
    return {
        "valid": valid,
        "epoch": registry.get("epoch"),
        "version": registry.get("version"),
        "generated_at_utc": registry.get("generated_at_utc"),
        "contract_count": len(contracts),
        "schema_errors": schema_errors,
        "duplicate_ids": duplicate_ids,
        "missing_paths": missing_paths,
        "declared_path_violations": declared_path_violations,
        "invalid_owner_component": invalid_owners,
        "invalid_applies_to_modes": invalid_modes,
        "registry_sha256": sha256_for_file(
            registry_path
            if registry_path is not None
            else (
                repo_root
                / "TRADING_OS_MASTER_CATALOGUE"
                / "02_METADATA_EPOCHS"
                / "02_M2_CONTRACT_REGISTRY"
                / "contract_registry.json"
            )
        ),
    }


def write_summary(result: dict, output_md: Path) -> None:
    lines = [
        "# M2 Contract Registry Verification Summary",
        "",
        f"- Valid: {result.get('valid')}",
        f"- Contracts: {result.get('contract_count')}",
        f"- Registry SHA256: {result.get('registry_sha256')}",
    ]
    if result.get("schema_errors"):
        lines.append("- Schema errors:")
        for error in result["schema_errors"]:
            lines.append(f"  - {error}")
    if result.get("duplicate_ids"):
        lines.append("- Duplicate IDs:")
        for dup in result["duplicate_ids"]:
            lines.append(f"  - {dup}")
    if result.get("missing_paths"):
        lines.append("- Missing paths:")
        for missing in result["missing_paths"]:
            lines.append(f"  - {missing['id']}: {missing['path']}")
    if result.get("declared_path_violations"):
        lines.append("- Declared path violations:")
        for violation in result["declared_path_violations"]:
            lines.append(
                f"  - {violation['id']}: {violation['path']} ({violation['reason']})"
            )
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M2 contract registry")
    parser.add_argument("--registry-path", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    result = verify_registry(args.registry_path)
    write_json(args.output_json, result)
    write_summary(result, args.output_md)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
