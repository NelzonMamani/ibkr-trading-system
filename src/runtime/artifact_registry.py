"""Canonical runtime artifact registry for E26."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
from typing import Any

from src.runtime.paths import get_data_dir, get_logs_dir, get_output_dir, resolve_repo_root


@dataclass(frozen=True)
class ArtifactEntry:
    name: str
    category: str
    root: str
    patterns: tuple[str, ...]
    purge_levels: tuple[str, ...]
    backup_included: bool


def build_registry() -> list[ArtifactEntry]:
    return [
        ArtifactEntry(
            name="runtime_db",
            category="REGENERABLE",
            root=str(get_data_dir()),
            patterns=("*.db", "*.sqlite", "*-wal", "*-shm", "*-journal"),
            purge_levels=("HARD",),
            backup_included=True,
        ),
        ArtifactEntry(
            name="runtime_logs",
            category="REGENERABLE",
            root=str(get_logs_dir()),
            patterns=("**/*",),
            purge_levels=("LIGHT", "STANDARD", "HARD"),
            backup_included=False,
        ),
        ArtifactEntry(
            name="runtime_output",
            category="REGENERABLE",
            root=str(get_output_dir()),
            patterns=("**/*",),
            purge_levels=("LIGHT", "STANDARD", "HARD"),
            backup_included=False,
        ),
        ArtifactEntry(
            name="runtime_caches",
            category="SEMI_PERSISTENT",
            root=str(get_data_dir()),
            patterns=("**/runtime_cache*", "**/*cache*.json"),
            purge_levels=("STANDARD", "HARD"),
            backup_included=True,
        ),
    ]


def registry_snapshot() -> dict[str, Any]:
    return {
        "repo_root": str(resolve_repo_root()),
        "entries": [asdict(entry) for entry in build_registry()],
    }


def write_registry_snapshot(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = registry_snapshot()
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return path
