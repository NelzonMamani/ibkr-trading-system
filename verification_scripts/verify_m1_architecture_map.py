"""Verify M1 Architecture Map boundaries and ownership.

This is a metadata-only verification script. It does not modify runtime behavior.
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class Component:
    name: str
    path: Path
    owner: str
    description: str


REQUIRED_COMPONENTS = [
    Component(
        name="core_orchestration",
        path=Path("src/core_engine"),
        owner="core_engine",
        description="Lifecycle control, run modes, orchestration, scheduling",
    ),
    Component(
        name="scanner",
        path=Path("src/scanner"),
        owner="scanner",
        description="Market discovery and watchlist/focus pipelines",
    ),
    Component(
        name="market_data",
        path=Path("src/market_data"),
        owner="market_data",
        description="Market data access and hubs",
    ),
    Component(
        name="data_hydration",
        path=Path("src/data"),
        owner="data",
        description="Data hydration and preprocessing",
    ),
    Component(
        name="patterns",
        path=Path("src/patterns"),
        owner="patterns",
        description="Pattern detection",
    ),
    Component(
        name="strategy_policy",
        path=Path("src/strategies"),
        owner="strategies",
        description="Strategy policy and intent generation",
    ),
    Component(
        name="risk_engine",
        path=Path("src/risk"),
        owner="risk",
        description="Risk gating and sizing",
    ),
    Component(
        name="execution_engine",
        path=Path("src/execution"),
        owner="execution",
        description="Order lifecycle and execution providers",
    ),
    Component(
        name="broker_adapters",
        path=Path("src/brokers"),
        owner="brokers",
        description="Broker adapter layer",
    ),
    Component(
        name="storage",
        path=Path("src/storage"),
        owner="storage",
        description="Persistence and audit trails",
    ),
]

DISALLOWED_IMPORTS = {
    "scanner": {"execution"},
    "patterns": {"execution", "broker", "brokers"},
    "strategies": {"execution", "broker", "brokers"},
    "strategy": {"execution", "broker", "brokers"},
    "risk": {"execution", "broker", "brokers"},
}


@dataclass
class ImportViolation:
    file: str
    module: str
    forbidden: str


def iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        yield path


def resolve_module_name(file_path: Path, src_root: Path) -> str:
    relative = file_path.relative_to(src_root)
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def resolve_relative_import(current_module: str, level: int, module: str | None) -> str:
    parts = current_module.split(".")
    if level > len(parts):
        return module or ""
    base = parts[: len(parts) - level]
    if module:
        base.extend(module.split("."))
    return ".".join(base)


def extract_imports(file_path: Path, src_root: Path) -> set[str]:
    content = file_path.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(file_path))
    current_module = resolve_module_name(file_path, src_root)
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src."):
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None and node.level == 0:
                continue
            if node.level > 0:
                resolved = resolve_relative_import(
                    current_module, node.level, node.module
                )
                if resolved:
                    imports.add(f"src.{resolved}")
            elif node.module and node.module.startswith("src."):
                imports.add(node.module)

    return imports


def top_level_module(module: str) -> str:
    return module.split(".")[1] if module.startswith("src.") else module.split(".")[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify M1 architecture boundaries")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"

    component_results = []
    for component in REQUIRED_COMPONENTS:
        exists = (repo_root / component.path).exists()
        component_results.append(
            {
                "name": component.name,
                "path": str(component.path),
                "owner": component.owner,
                "description": component.description,
                "exists": exists,
            }
        )

    violations: list[ImportViolation] = []
    for module_root, forbidden in DISALLOWED_IMPORTS.items():
        module_path = src_root / module_root
        if not module_path.exists():
            continue
        for file_path in iter_python_files(module_path):
            imports = extract_imports(file_path, src_root)
            for imported in imports:
                top_level = top_level_module(imported)
                if top_level in forbidden:
                    violations.append(
                        ImportViolation(
                            file=str(file_path.relative_to(repo_root)),
                            module=module_root,
                            forbidden=top_level,
                        )
                    )

    result = {
        "components": component_results,
        "violations": [violation.__dict__ for violation in violations],
        "summary": {
            "components_missing": [
                comp["path"] for comp in component_results if not comp["exists"]
            ],
            "violation_count": len(violations),
        },
        "status": "PASS" if not violations else "FAIL",
    }

    if args.output_json:
        args.output_json.write_text(
            json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
        )

    if args.output_md:
        missing = result["summary"]["components_missing"]
        md_lines = [
            "# M1 Architecture Map Verification Summary",
            "",
            f"Status: **{result['status']}**",
            "",
            "## Component Presence",
        ]
        for comp in component_results:
            status = "OK" if comp["exists"] else "MISSING"
            md_lines.append(f"- {comp['name']} ({comp['path']}): {status}")
        md_lines.append("")
        md_lines.append("## Boundary Violations")
        if violations:
            for violation in violations:
                md_lines.append(
                    f"- {violation.file}: {violation.module} imports {violation.forbidden}"
                )
        else:
            md_lines.append("- None detected")
        if missing:
            md_lines.append("")
            md_lines.append("## Missing Components")
            for item in missing:
                md_lines.append(f"- {item}")
        args.output_md.write_text("\n".join(md_lines), encoding="utf-8")

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
