from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Sequence

CANONICAL_PREFIXES = ("SF_", "XL_", "C_", "K_")


def get_repo_root(start_path: Path | None = None) -> Path:
    if start_path is None:
        start_path = Path(__file__).resolve()
    for parent in [start_path] + list(start_path.parents):
        if (parent / "TRADING_OS_MASTER_CATALOGUE").exists():
            return parent
    raise RuntimeError("Repository root not found from start path")


def _sorted_rel_paths(repo_root: Path, paths: Iterable[Path]) -> list[str]:
    return sorted(str(path.relative_to(repo_root)) for path in paths)


def list_core_epoch_governance_paths(repo_root: Path) -> list[str]:
    core_root = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "01_CORE_EPOCHS"
    if not core_root.exists():
        return []
    governance_dirs = [
        path / "governance" for path in core_root.iterdir() if (path / "governance").exists()
    ]
    return _sorted_rel_paths(repo_root, governance_dirs)


def list_metadata_epoch_governance_paths(repo_root: Path) -> list[str]:
    meta_root = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "02_METADATA_EPOCHS"
    if not meta_root.exists():
        return []
    governance_dirs = [
        path / "governance" for path in meta_root.iterdir() if (path / "governance").exists()
    ]
    return _sorted_rel_paths(repo_root, governance_dirs)


def collect_strategy_policy_docs(repo_root: Path) -> list[str]:
    patterns = ["STRATEGY_*.md", "ROSS_*.md"]
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(repo_root.glob(pattern))
    return _sorted_rel_paths(repo_root, matches)


def collect_runtime_config_paths(repo_root: Path) -> list[str]:
    candidates = [repo_root / "src" / "config", repo_root / "config", repo_root / "data" / "config"]
    return _sorted_rel_paths(repo_root, [path for path in candidates if path.exists()])


def collect_generated_artifact_paths(repo_root: Path) -> list[str]:
    candidates = [repo_root / "logs", repo_root / "output"]
    return _sorted_rel_paths(repo_root, [path for path in candidates if path.exists()])


def list_canonical_sources(repo_root: Path | None = None) -> list[dict]:
    repo_root = get_repo_root(repo_root)
    sources: list[dict] = []

    sources.append(
        {
            "id": "system_constitution",
            "label": "SYSTEM_CONSTITUTION.md",
            "paths": [str((repo_root / "SYSTEM_CONSTITUTION.md").relative_to(repo_root))],
            "precedence": 1,
        }
    )
    sources.append(
        {
            "id": "master_catalogue",
            "label": "TRADING_OS_MASTER_CATALOGUE",
            "paths": [str((repo_root / "TRADING_OS_MASTER_CATALOGUE").relative_to(repo_root))],
            "precedence": 2,
        }
    )
    sources.append(
        {
            "id": "core_epoch_governance",
            "label": "Core Epoch Governance bundles",
            "paths": list_core_epoch_governance_paths(repo_root),
            "precedence": 3,
        }
    )
    sources.append(
        {
            "id": "metadata_epoch_governance",
            "label": "Metadata Epoch Governance bundles",
            "paths": list_metadata_epoch_governance_paths(repo_root),
            "precedence": 4,
        }
    )
    sources.append(
        {
            "id": "strategy_policy_documents",
            "label": "Strategy Policy documents",
            "paths": collect_strategy_policy_docs(repo_root),
            "precedence": 5,
        }
    )
    sources.append(
        {
            "id": "runtime_configuration",
            "label": "Runtime configuration (mode-scoped)",
            "paths": collect_runtime_config_paths(repo_root),
            "precedence": 6,
        }
    )
    sources.append(
        {
            "id": "generated_artifacts",
            "label": "Generated artifacts (logs, reports)",
            "paths": collect_generated_artifact_paths(repo_root),
            "precedence": 7,
        }
    )
    return sources


def verify_identity_uniqueness(items: Sequence[dict], key: str) -> dict:
    seen: set[str] = set()
    duplicates: list[str] = []
    for item in items:
        value = str(item.get(key))
        if value in seen:
            duplicates.append(value)
        seen.add(value)
    return {"duplicates": sorted(set(duplicates)), "unique": not duplicates}


def validate_canonical_names(names: Sequence[str]) -> dict:
    invalid_prefix = [name for name in names if not name.startswith(CANONICAL_PREFIXES)]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    return {
        "invalid_prefix": sorted(invalid_prefix),
        "duplicates": duplicates,
        "valid": not invalid_prefix and not duplicates,
    }


def parse_naming_prefixes(governance_text: str) -> list[str]:
    prefixes: list[str] = []
    for line in governance_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("-") and "(" in stripped and "_" in stripped:
            token = stripped.split("(")[0].replace("-", "").strip()
            token = token.replace("*", "")
            if token.endswith("_"):
                prefixes.append(token)
    return prefixes


def build_canonical_registry(repo_root: Path | None = None, timestamp: str | None = None) -> dict:
    repo_root = get_repo_root(repo_root)
    registry = {
        "timestamp": timestamp,
        "sources": list_canonical_sources(repo_root),
        "naming_rules": {"prefixes": list(CANONICAL_PREFIXES)},
    }
    return registry


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def sha256_for_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def update_system_state_statuses(state_file: Path, updates: dict[str, str]) -> bool:
    if not state_file.exists() or not updates:
        return False

    pattern = re.compile(r"^(\s*-\s+)([ME]\d+_[A-Z0-9_]+)(:\s+)([A-Z_]+)(\s*)$")
    changed = False
    rendered: list[str] = []
    for raw_line in state_file.read_text(encoding="utf-8").splitlines():
        match = pattern.match(raw_line)
        if not match:
            rendered.append(raw_line)
            continue
        epoch = match.group(2)
        if epoch not in updates:
            rendered.append(raw_line)
            continue
        next_status = updates[epoch]
        if match.group(4) != next_status:
            changed = True
        rendered.append(f"{match.group(1)}{epoch}{match.group(3)}{next_status}{match.group(5)}")

    if changed:
        state_file.write_text("\n".join(rendered) + "\n", encoding="utf-8")
    return changed
