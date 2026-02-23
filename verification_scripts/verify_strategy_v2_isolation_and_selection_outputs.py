#!/usr/bin/env python3
from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SURFACES = [
    "selection_plan",
    "stock_selection_law",
    "ranking_model",
    "risk_model",
    "execution_model",
    "trailing_model",
    "exit_model",
]

RUNTIME_PATTERNS = {
    "selection_plan": [r"\\.selection_plan", r"selection_plan"],
    "stock_selection_law": [r"\\.stock_selection_law", r"stock_selection_law"],
    "ranking_model": [r"\\.ranking_model", r"ranking_model"],
    "risk/exit/trailing": [r"\\.risk_model", r"\\.exit_model", r"\\.trailing_model", r"risk_model", r"exit_model", r"trailing_model"],
}


def find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for path in [cur, *cur.parents]:
        if (path / ".git").exists() and (path / "src").exists():
            return path
    raise RuntimeError(f"Could not detect repo root from {start}")


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class TeeLogger:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def log(self, msg: str) -> None:
        print(msg)
        self.lines.append(msg)

    def dump(self, path: Path) -> None:
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def canonical_json_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def dataclass_to_obj(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [dataclass_to_obj(v) for v in value]
    if isinstance(value, list):
        return [dataclass_to_obj(v) for v in value]
    if isinstance(value, dict):
        return {str(k): dataclass_to_obj(v) for k, v in value.items()}
    return value


def parse_policy_sources(policy_file: Path) -> dict[str, dict[str, Any]]:
    source = policy_file.read_text(encoding="utf-8")
    tree = ast.parse(source)
    results: dict[str, dict[str, Any]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            target_names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if "POLICY_V2" in target_names and isinstance(node.value, ast.Call):
                for kw in node.value.keywords:
                    if kw.arg in SURFACES or kw.arg in {"identity", "session_semantics", "mode_semantics"}:
                        seg = ast.get_source_segment(source, kw.value)
                        results[kw.arg] = {
                            "file": str(policy_file),
                            "line": kw.value.lineno,
                            "end_line": getattr(kw.value, "end_lineno", kw.value.lineno),
                            "code": seg,
                        }
    return results


def discover_strategies(repo_root: Path) -> list[dict[str, str]]:
    out = subprocess.check_output(
        [
            "rg",
            "-n",
            "POLICY_V2\\s*=\\s*StrategyPolicyV2\\(",
            "src/strategies",
        ],
        cwd=repo_root,
        text=True,
    )
    catalogue = repo_root / "TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES"
    slug_to_id: dict[str, str] = {}
    if catalogue.exists():
        for d in sorted(catalogue.iterdir()):
            if d.is_dir() and re.match(r"P\d{2}_", d.name):
                sid, raw = d.name.split("_", 1)
                slug_to_id[raw.lower()] = sid

    entries: list[dict[str, str]] = []
    for line in out.splitlines():
        file_path, line_no, _ = line.split(":", 2)
        p = Path(file_path)
        slug = p.parent.name
        sid = slug_to_id.get(slug, "UNKNOWN")
        entries.append(
            {
                "strategy_id": sid,
                "slug": slug,
                "module": f"src.strategies.{slug}.strategy_policy_v2",
                "policy_path": file_path,
                "policy_line": line_no,
            }
        )
    entries.sort(key=lambda x: (x["strategy_id"], x["slug"]))
    return entries


def inventory_from_occurrences(repo_root: Path) -> dict[str, Any]:
    all_hits = subprocess.check_output(
        ["rg", "-n", "StrategyPolicyV2\\(", "src", "TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES"],
        cwd=repo_root,
        text=True,
    ).splitlines()
    policy_hits = subprocess.check_output(
        ["rg", "-n", "POLICY_V2\\s*=\\s*StrategyPolicyV2\\(", "src/strategies"],
        cwd=repo_root,
        text=True,
    ).splitlines()
    return {
        "searches": {
            "POLICY_V2 = StrategyPolicyV2(": policy_hits,
            "StrategyPolicyV2(": all_hits,
        }
    }


def find_runtime_references(repo_root: Path) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "search_roots": ["src"],
        "surfaces": {},
        "grep_evidence": [],
    }
    for surface_name, patterns in RUNTIME_PATTERNS.items():
        refs: list[dict[str, Any]] = []
        for pattern in patterns:
            cmd = ["rg", "-n", pattern, "src"]
            cp = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True)
            trace["grep_evidence"].append({"command": " ".join(cmd), "returncode": cp.returncode})
            for line in cp.stdout.splitlines():
                file_path, line_no, text = line.split(":", 2)
                if file_path.endswith("strategy_policy_v2.py"):
                    continue
                refs.append({"file": file_path, "line": int(line_no), "match": text.strip(), "pattern": pattern})
        unique = {(r["file"], r["line"], r["match"]) for r in refs}
        compact = [{"file": f, "line": l, "match": m} for (f, l, m) in sorted(unique)]
        trace["surfaces"][surface_name] = compact
    return trace


def try_selection_output(repo_root: Path, slug: str, runtime_refs: dict[str, Any]) -> dict[str, Any]:
    # Best-effort safe path: no broker calls. We only invoke zero-arg selection-like functions if present.
    sys.path.insert(0, str(repo_root))
    candidates = [
        f"src.strategies.{slug}.selection",
        f"src.strategies.{slug}.selector",
        f"src.strategies.{slug}.scanner_policy",
        f"src.strategies.{slug}.strategy",
    ]
    tried_modules: list[str] = []
    errors: list[str] = []
    for mod_name in candidates:
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:
            errors.append(f"{mod_name}: import failed ({exc.__class__.__name__}: {exc})")
            continue
        tried_modules.append(mod_name)
        for attr_name in dir(mod):
            if not re.search(r"(select|selection|watchlist|focus|candidate|rebalance)", attr_name, re.IGNORECASE):
                continue
            fn = getattr(mod, attr_name)
            if not callable(fn):
                continue
            try:
                import inspect

                sig = inspect.signature(fn)
                required = [
                    p for p in sig.parameters.values()
                    if p.default is inspect._empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                ]
                if required:
                    continue
                result = fn()  # noqa: S307 - controlled local call
                obj = dataclass_to_obj(result)
                return {
                    "selection_output_unavailable": False,
                    "producer": f"{mod_name}.{attr_name}",
                    "output": obj,
                }
            except Exception as exc:
                errors.append(f"{mod_name}.{attr_name}() failed ({exc.__class__.__name__}: {exc})")

    expected_paths = []
    for key in ("selection_plan", "stock_selection_law", "ranking_model"):
        for ref in runtime_refs["surfaces"].get(key, []):
            expected_paths.append(f"{ref['file']}:{ref['line']}")
    return {
        "selection_output_unavailable": True,
        "reason": "No safe, zero-argument selection producer callable found without external services.",
        "modules_tried": tried_modules,
        "errors": errors[:25],
        "expected_producer_code_path": sorted(set(expected_paths)),
    }


def write_policy_diff_matrix(path: Path, policy_dump: dict[str, Any]) -> None:
    rows = []
    collisions: dict[str, dict[str, list[str]]] = {s: defaultdict(list) for s in SURFACES}
    for strat in policy_dump["strategies"]:
        row = {"strategy": f"{strat['strategy_id']}:{strat['slug']}"}
        for surface in SURFACES:
            h = canonical_json_hash(strat.get(surface))
            row[surface] = h
            collisions[surface][h].append(row["strategy"])
        rows.append(row)

    headers = ["Strategy", *SURFACES]
    lines = ["# POLICY_DIFF_MATRIX", "", "| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append(
            "| " + " | ".join([row["strategy"], *[row[s] for s in SURFACES]]) + " |"
        )

    lines.append("\n## Collision list (identical canonical JSON hash by surface)")
    for surface in SURFACES:
        lines.append(f"\n### {surface}")
        groups = [v for v in collisions[surface].values() if len(v) > 1]
        if not groups:
            lines.append("- No collisions.")
            continue
        for grp in groups:
            lines.append(f"- {', '.join(sorted(grp))}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_runtime_trace(path: Path, runtime_trace: dict[str, Any]) -> None:
    lines = ["# RUNTIME_WIRING_TRACE", "", "## Search roots", "- src", "", "## Surface consumption evidence"]
    for surface, refs in runtime_trace["surfaces"].items():
        lines.append(f"\n### {surface}")
        if refs:
            for ref in refs:
                lines.append(f"- `{ref['file']}:{ref['line']}` -> `{ref['match']}`")
        else:
            lines.append(f"- Policy surface {surface} appears unconsumed by runtime. No references found.")
    lines.append("\n## Grep evidence")
    for cmd in runtime_trace["grep_evidence"]:
        lines.append(f"- `{cmd['command']}` (exit={cmd['returncode']})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    repo_root = find_repo_root(Path.cwd())
    os.chdir(repo_root)
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    logger = TeeLogger()
    logger.log("Using skill(s): none (task does not match available skill-installer/skill-creator scopes).")
    logger.log(f"Repo root: {repo_root}")

    timestamp = utc_ts()
    out_dir = repo_root / "TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/STRATEGY_POLICY_V2_ISOLATION_AUDIT" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.log(f"Output directory: {out_dir}")

    inventory = inventory_from_occurrences(repo_root)
    discovered = discover_strategies(repo_root)
    logger.log(f"Discovered {len(discovered)} StrategyPolicyV2 strategy modules.")

    policy_payload: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "inventory": inventory,
        "strategies": [],
    }

    runtime_trace = find_runtime_references(repo_root)

    for entry in discovered:
        mod = importlib.import_module(entry["module"])
        policy = getattr(mod, "POLICY_V2")
        policy_path = repo_root / entry["policy_path"]
        source_map = parse_policy_sources(policy_path)

        payload = {
            "strategy_id": entry["strategy_id"],
            "slug": entry["slug"],
            "module": entry["module"],
            "policy_object": "POLICY_V2",
            "policy_path": entry["policy_path"],
            "source_surfaces": source_map,
            "identity": dataclass_to_obj(policy.identity),
            "selection_plan": dataclass_to_obj(policy.selection_plan),
            "stock_selection_law": dataclass_to_obj(policy.stock_selection_law),
            "ranking_model": dataclass_to_obj(policy.ranking_model),
            "risk_model": dataclass_to_obj(policy.risk_model),
            "execution_model": dataclass_to_obj(policy.execution_model),
            "trailing_model": dataclass_to_obj(policy.trailing_model),
            "exit_model": dataclass_to_obj(policy.exit_model),
            "session_semantics": dataclass_to_obj(policy.session_semantics),
            "mode_semantics": dataclass_to_obj(policy.mode_semantics),
        }
        policy_payload["strategies"].append(payload)

    policy_payload["strategies"].sort(key=lambda x: (x["strategy_id"], x["slug"]))

    selection_outputs: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "strategies": [],
    }
    for strategy in policy_payload["strategies"]:
        out = try_selection_output(repo_root, strategy["slug"], runtime_trace)
        selection_outputs["strategies"].append(
            {
                "strategy_id": strategy["strategy_id"],
                "slug": strategy["slug"],
                **out,
            }
        )

    (out_dir / "POLICY_DUMP.json").write_text(json.dumps(policy_payload, indent=2), encoding="utf-8")
    write_policy_diff_matrix(out_dir / "POLICY_DIFF_MATRIX.md", policy_payload)
    write_runtime_trace(out_dir / "RUNTIME_WIRING_TRACE.md", runtime_trace)
    (out_dir / "SELECTION_OUTPUTS.json").write_text(json.dumps(selection_outputs, indent=2), encoding="utf-8")

    logger.log("Artifacts written:")
    for file_name in ["POLICY_DUMP.json", "POLICY_DIFF_MATRIX.md", "RUNTIME_WIRING_TRACE.md", "SELECTION_OUTPUTS.json"]:
        logger.log(f"- {out_dir / file_name}")

    logger.dump(out_dir / "console_log.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
