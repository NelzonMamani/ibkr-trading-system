"""
Auto-generate configuration documentation from CONFIG_REGISTRY.
"""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.config.config_registry import CONFIG_REGISTRY


def _format_default(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, (list, set, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return str(value)
    return str(value)


def _resolve_default(entry: Dict[str, Any]) -> str:
    if "default_factory" in entry:
        return _format_default(entry["default_factory"]())
    return _format_default(entry.get("default"))


def _iter_affects(entry: Dict[str, Any]) -> Iterable[str]:
    affects = entry.get("affects", [])
    return affects or ["Uncategorized"]


def _group_by_subsystem() -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    for name, entry in CONFIG_REGISTRY.items():
        for subsystem in _iter_affects(entry):
            grouped.setdefault(subsystem, []).append(name)
    for subsystem in grouped:
        grouped[subsystem].sort()
    return dict(sorted(grouped.items()))


def _render_reference() -> str:
    grouped = _group_by_subsystem()
    lines = [
        "# Configuration Reference",
        "",
        "Generated from `src/config/config_registry.py`.",
        "",
    ]
    for subsystem, keys in grouped.items():
        lines.append(f"## {subsystem}")
        lines.append("")
        for key in keys:
            entry = CONFIG_REGISTRY[key]
            env_names = ", ".join(entry.get("env", [])) or "(none)"
            lines.append(f"### {key}")
            lines.append("")
            lines.append(f"* **Type:** {entry.get('type')}")
            lines.append(f"* **Default:** `{_resolve_default(entry)}`")
            lines.append(f"* **Env overrides:** `{env_names}`")
            lines.append(f"* **Enforcement:** {entry.get('enforcement')}")
            lines.append(f"* **Mutable:** {entry.get('mutable')}")
            if entry.get("choices"):
                lines.append(f"* **Choices:** {entry.get('choices')}")
            lines.append(f"* **Description:** {entry.get('description')}")
            lines.append("")
    return "\n".join(lines)


def _render_authority() -> str:
    hard = sum(1 for entry in CONFIG_REGISTRY.values() if entry.get("enforcement") == "HARD")
    soft = sum(1 for entry in CONFIG_REGISTRY.values() if entry.get("enforcement") == "SOFT")
    advisory = sum(1 for entry in CONFIG_REGISTRY.values() if entry.get("enforcement") == "ADVISORY")
    total = len(CONFIG_REGISTRY)
    lines = [
        "# Phase 24 — Configuration Authority",
        "",
        "This document explains why configuration is centralized and enforced.",
        "",
        "## Why this exists",
        "",
        "Configuration is now resolved through a single registry and resolver to eliminate",
        "implicit defaults, hidden environment dependencies, and runtime ambiguity.",
        "",
        "## What changed",
        "",
        f"* **Registry size:** {total} variables",
        f"* **HARD enforced:** {hard}",
        f"* **SOFT:** {soft}",
        f"* **ADVISORY:** {advisory}",
        "",
        "## How ambiguity was eliminated",
        "",
        "* All modules read configuration via `get_config` and the resolver.",
        "* Environment variables are parsed once and validated for type/constraints.",
        "* Derived values (e.g. effective run mode) are explicitly recorded.",
        "* A structured CONFIG_RESOLVED event is emitted at startup.",
        "",
        "## Future extension pattern",
        "",
        "1. Add a new entry to `CONFIG_REGISTRY` with type, default, env overrides, and metadata.",
        "2. Add enforcement rules or validation in `config_resolver` if needed.",
        "3. Regenerate documentation by running the config docs generator.",
        "",
    ]
    return "\n".join(lines)


def _render_env_checklist() -> str:
    lines = [
        "# Environment Variables Checklist",
        "",
        "One line per variable, grouped by required vs optional.",
        "",
        "## REQUIRED",
        "",
    ]
    required: List[str] = []
    optional: List[str] = []
    seen = set()
    for name, entry in CONFIG_REGISTRY.items():
        env_names = entry.get("env", [])
        if not env_names:
            continue
        enforcement = entry.get("enforcement")
        default_present = "default" in entry or "default_factory" in entry
        allow_none = entry.get("allow_none") is True
        is_required = enforcement == "HARD" and not default_present and not allow_none
        for env_name in env_names:
            if env_name in seen:
                continue
            seen.add(env_name)
            if is_required:
                required.append(env_name)
            else:
                optional.append(env_name)
    required.sort()
    optional.sort()
    if required:
        for env_name in required:
            lines.append(f"- {env_name}")
    else:
        lines.append("(none)")
    lines.extend(["", "## OPTIONAL", ""]) 
    for env_name in optional:
        lines.append(f"- {env_name}")
    lines.append("")
    return "\n".join(lines)


def generate_docs(docs_dir: Path) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "CONFIGURATION_REFERENCE.md").write_text(
        _render_reference(), encoding="utf-8"
    )
    (docs_dir / "PHASE_24_CONFIGURATION_AUTHORITY.md").write_text(
        _render_authority(), encoding="utf-8"
    )
    (docs_dir / "ENVIRONMENT_VARIABLES_CHECKLIST.md").write_text(
        _render_env_checklist(), encoding="utf-8"
    )


if __name__ == "__main__":
    generate_docs(Path("docs"))
