from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from src.metadata.m0_canon_helpers import get_repo_root

ALLOWED_CONTRACT_TYPES = {"interface", "schema", "artifact", "protocol"}
ALLOWED_OWNER_COMPONENTS = {
    "core_engine",
    "scanner",
    "market_data",
    "data",
    "patterns",
    "signals",
    "strategies",
    "risk",
    "execution",
    "brokers",
    "storage",
    "metadata",
}
ALLOWED_AUTHORITIES = {"authoritative", "non_authoritative"}
ALLOWED_STATUSES = {"implemented", "partial", "declared"}
ALLOWED_MODES = {"SIM", "PAPER", "READ_ONLY", "LIVE"}
REQUIRED_CONTRACT_FIELDS = {
    "id",
    "name",
    "type",
    "owner_component",
    "authority",
    "paths",
    "applies_to_modes",
    "status",
    "notes",
}


def _default_registry_path(repo_root: Path) -> Path:
    return (
        repo_root
        / "TRADING_OS_MASTER_CATALOGUE"
        / "02_METADATA_EPOCHS"
        / "02_M2_CONTRACT_REGISTRY"
        / "contract_registry.json"
    )


def load_registry(path: Path | None = None) -> dict:
    repo_root = get_repo_root(Path(__file__).resolve())
    registry_path = path or _default_registry_path(repo_root)
    return json.loads(registry_path.read_text(encoding="utf-8"))


def _ensure_string_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return value


def _validate_contract(contract: dict) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_CONTRACT_FIELDS - set(contract.keys())
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")
    contract_id = contract.get("id")
    if not isinstance(contract_id, str) or not contract_id.startswith("C_"):
        errors.append("id must be a string starting with C_")
    if contract.get("type") not in ALLOWED_CONTRACT_TYPES:
        errors.append("type must be interface|schema|artifact|protocol")
    if contract.get("owner_component") not in ALLOWED_OWNER_COMPONENTS:
        errors.append("owner_component must be in allowed set")
    if contract.get("authority") not in ALLOWED_AUTHORITIES:
        errors.append("authority must be authoritative|non_authoritative")
    if contract.get("status") not in ALLOWED_STATUSES:
        errors.append("status must be implemented|partial|declared")
    paths = _ensure_string_list(contract.get("paths"))
    if paths is None or not paths:
        errors.append("paths must be a non-empty list of strings")
    modes = _ensure_string_list(contract.get("applies_to_modes"))
    if modes is None or not modes:
        errors.append("applies_to_modes must be a non-empty list of strings")
    elif not set(modes).issubset(ALLOWED_MODES):
        errors.append("applies_to_modes must be subset of SIM,PAPER,READ_ONLY,LIVE")
    return errors


def validate_registry(registry: dict) -> list[str]:
    errors: list[str] = []
    if registry.get("epoch") != "M2_CONTRACT_REGISTRY":
        errors.append("epoch must be M2_CONTRACT_REGISTRY")
    if not isinstance(registry.get("version"), str):
        errors.append("version must be string")
    if not isinstance(registry.get("generated_at_utc"), str):
        errors.append("generated_at_utc must be string")
    contracts = registry.get("contracts")
    if not isinstance(contracts, list):
        errors.append("contracts must be list")
        return errors
    for idx, contract in enumerate(contracts):
        if not isinstance(contract, dict):
            errors.append(f"contracts[{idx}] must be object")
            continue
        contract_errors = _validate_contract(contract)
        for error in contract_errors:
            errors.append(f"{contract.get('id', f'index_{idx}')}: {error}")
    return errors


def find_duplicate_ids(contracts: Iterable[dict]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for contract in contracts:
        contract_id = str(contract.get("id"))
        if contract_id in seen:
            duplicates.add(contract_id)
        seen.add(contract_id)
    return sorted(duplicates)
