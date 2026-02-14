from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "src" / "integrity" / "epoch_verification_registry.yaml"
AUDIT_ROOT = REPO_ROOT / "output" / "audit" / "e23"
CANONICAL_RUN_MODES = ["SIM", "PAPER", "READ_ONLY", "LIVE"]


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout_path: str
    stderr_path: str


@dataclass
class DriftItem:
    severity: str
    code: str
    summary: str
    evidence: str
    auto_fix_applied: bool = False


class E23Runner:
    def __init__(self, max_loops: int = 5) -> None:
        self.max_loops = max_loops
        self.timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.audit_dir = AUDIT_ROOT / self.timestamp
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.drift_items: list[DriftItem] = []
        self.inventory_drifts: list[DriftItem] = []
        self.fix_actions: list[dict[str, str]] = []

    def run(self) -> int:
        registry = self._load_registry()
        inventory = self._discover_inventory(registry)

        final_results: list[CommandResult] = []
        coherent = False
        for loop_idx in range(1, self.max_loops + 1):
            loop_results = self._run_mandatory_verifications(loop_idx)
            final_results = loop_results
            loop_drifts = self.inventory_drifts + self._detect_drift(loop_results)
            self.drift_items = loop_drifts
            if not loop_drifts:
                coherent = True
                break
            fixed = self._apply_safe_fixes(loop_drifts)
            remaining_hard = [d for d in loop_drifts if d.severity == "HARD" and not d.auto_fix_applied]
            if remaining_hard and not fixed:
                break
            if not remaining_hard and not fixed:
                coherent = True
                break

        state = self._build_integrity_state(inventory, final_results, coherent)
        self._write_truth_artifacts(state, inventory, final_results)
        return 0 if state["platform_state"] not in {"DRIFT_DETECTED", "INVARIANT_VIOLATION"} else 1

    def _load_registry(self) -> dict[str, Any]:
        if not REGISTRY_PATH.exists():
            raise FileNotFoundError(f"Missing verification registry: {REGISTRY_PATH}")
        raw = REGISTRY_PATH.read_text(encoding="utf-8")
        if yaml is not None:
            return yaml.safe_load(raw) or {}
        return self._simple_yaml_load(raw)

    def _simple_yaml_load(self, raw: str) -> dict[str, Any]:
        # Fallback loader for minimal nested dicts in this repository's registry format.
        parsed: dict[str, Any] = {}
        current: dict[str, Any] | None = None
        current_key = ""
        for line in raw.splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            if not line.startswith(" ") and line.endswith(":"):
                current_key = line.rstrip(":").strip()
                parsed[current_key] = {}
                current = parsed[current_key]
                continue
            if current is None:
                continue
            m = re.match(r"\s{2}([A-Z0-9]+):\s*\{(.*)\}\s*$", line)
            if not m:
                continue
            item_key = m.group(1)
            item_raw = m.group(2)
            status_match = re.search(r'"?status"?\s*:\s*([^,}]+)', item_raw)
            strategy_match = re.search(r'"?strategy"?\s*:\s*([^,}]+)', item_raw)
            verification_match = re.search(r'"?verification"?\s*:\s*(\[[^\]]*\])', item_raw)
            item: dict[str, Any] = {}
            if status_match:
                item["status"] = status_match.group(1).strip().strip("\"'")
            if strategy_match:
                item["strategy"] = strategy_match.group(1).strip().strip("\"'")
            if verification_match:
                cmds = [c.strip().strip("\"'") for c in verification_match.group(1).strip('[]').split(',') if c.strip()]
                item["verification"] = cmds
            current[item_key] = item
        return parsed

    def _discover_inventory(self, registry: dict[str, Any]) -> dict[str, Any]:
        core_registry = registry.get("core_epochs") or {}
        metadata_registry = registry.get("metadata_epochs") or {}
        strategy_registry = registry.get("strategies") or {}

        core = {
            f"E{i}": str(core_registry.get(f"E{i}", {}).get("status", "UNIMPLEMENTED")).upper()
            for i in range(23)
        }
        metadata = {
            f"M{i}": str(metadata_registry.get(f"M{i}", {}).get("status", "UNIMPLEMENTED")).upper()
            for i in range(11)
        }
        strategies = {
            f"P{i:02d}": str(strategy_registry.get(f"P{i:02d}", {}).get("status", "UNIMPLEMENTED")).upper()
            for i in range(1, 21)
        }

        for key in core:
            if key not in core_registry:
                self.inventory_drifts.append(
                    DriftItem("SOFT", "MISSING_REGISTRY_ENTRY", f"Missing core registry entry: {key}", "registry")
                )
        for key in metadata:
            if key not in metadata_registry:
                self.inventory_drifts.append(
                    DriftItem("SOFT", "MISSING_REGISTRY_ENTRY", f"Missing metadata registry entry: {key}", "registry")
                )
        for key in strategies:
            if key not in strategy_registry:
                self.inventory_drifts.append(
                    DriftItem("SOFT", "MISSING_REGISTRY_ENTRY", f"Missing strategy registry entry: {key}", "registry")
                )

        return {"core_epochs": core, "metadata_epochs": metadata, "strategies": strategies}

    def _run_command(self, cmd: str, label: str) -> CommandResult:
        stdout_path = self.audit_dir / f"{label}.stdout.log"
        stderr_path = self.audit_dir / f"{label}.stderr.log"
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            shell=True,
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        stdout_path.write_text(proc.stdout or "", encoding="utf-8")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8")
        return CommandResult(cmd, proc.returncode, str(stdout_path.relative_to(REPO_ROOT)), str(stderr_path.relative_to(REPO_ROOT)))

    def _run_mandatory_verifications(self, loop_idx: int) -> list[CommandResult]:
        commands = [
            "python -m compileall src",
            "pytest -q",
            "python -m src.main --mode SIM --cycles 1",
            "python -m src.main --mode PAPER --cycles 1",
            "python -m src.main --mode READ_ONLY --cycles 1",
            "python -m src.main --mode LIVE --cycles 1",
        ]
        results: list[CommandResult] = []
        for idx, command in enumerate(commands, start=1):
            label = f"loop{loop_idx:02d}_{idx:02d}"
            results.append(self._run_command(command, label))
        return results

    def _detect_drift(self, results: list[CommandResult]) -> list[DriftItem]:
        drift: list[DriftItem] = []
        for result in results:
            if result.returncode != 0:
                drift.append(
                    DriftItem(
                        severity="HARD",
                        code="VERIFICATION_FAILURE",
                        summary=f"Command failed: {result.command}",
                        evidence=result.stdout_path,
                    )
                )

        main_file = (REPO_ROOT / "src" / "main.py").read_text(encoding="utf-8")
        if '            "READONLY",' in main_file:
            drift.append(
                DriftItem(
                    severity="SOFT",
                    code="NON_CANONICAL_ALIAS_EXPOSED",
                    summary="READONLY alias exposed directly in argparse choices",
                    evidence="src/main.py",
                )
            )

        read_only_result = next((r for r in results if "--mode READ_ONLY" in r.command), None)
        paper_result = next((r for r in results if "--mode PAPER" in r.command), None)
        live_result = next((r for r in results if "--mode LIVE" in r.command), None)
        if read_only_result:
            output = (REPO_ROOT / read_only_result.stdout_path).read_text(encoding="utf-8", errors="ignore")
            if "[SAFETY] ORDER ROUTING: BLOCKED" not in output:
                drift.append(
                    DriftItem(
                        severity="HARD",
                        code="READ_ONLY_ROUTING_UNSAFE",
                        summary="READ_ONLY run did not prove routing blocked.",
                        evidence=read_only_result.stdout_path,
                    )
                )
        if paper_result:
            output = (REPO_ROOT / paper_result.stdout_path).read_text(encoding="utf-8", errors="ignore")
            if "RUN_MODE: PAPER" not in output:
                drift.append(
                    DriftItem(
                        severity="HARD",
                        code="PAPER_MODE_UNVERIFIED",
                        summary="PAPER run did not resolve PAPER mode.",
                        evidence=paper_result.stdout_path,
                    )
                )
        if live_result:
            output = (REPO_ROOT / live_result.stdout_path).read_text(encoding="utf-8", errors="ignore")
            if "[SAFETY] ORDER ROUTING: BLOCKED" not in output:
                drift.append(
                    DriftItem(
                        severity="HARD",
                        code="LIVE_EXECUTION_SAFETY_UNVERIFIED",
                        summary="LIVE run did not prove execution-disabled safety gate.",
                        evidence=live_result.stdout_path,
                    )
                )
        return drift

    def _apply_safe_fixes(self, drift_items: list[DriftItem]) -> bool:
        changed = False
        for item in drift_items:
            if item.code == "NON_CANONICAL_ALIAS_EXPOSED":
                main_path = REPO_ROOT / "src" / "main.py"
                content = main_path.read_text(encoding="utf-8")
                updated = content.replace('            "READONLY",\n', "")
                if updated != content:
                    main_path.write_text(updated, encoding="utf-8")
                    changed = True
                    item.auto_fix_applied = True
                    self.fix_actions.append(
                        {
                            "drift": item.code,
                            "action": "Removed READONLY alias from canonical argparse choices while retaining normalization logic.",
                        }
                    )
        return changed

    def _build_integrity_state(self, inventory: dict[str, Any], results: list[CommandResult], coherent: bool) -> dict[str, Any]:
        git_commit = "unknown"
        try:
            git_commit = (
                subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
            )
        except Exception:
            pass

        hard_drifts = [d for d in self.drift_items if d.severity == "HARD"]
        if any(d.code in {"READ_ONLY_ROUTING_UNSAFE", "VERIFICATION_FAILURE"} for d in hard_drifts):
            platform_state = "INVARIANT_VIOLATION"
        elif hard_drifts:
            platform_state = "DRIFT_DETECTED"
        elif coherent:
            platform_state = "TRADING_READY_PAPER"
        else:
            platform_state = "NOT_READY"

        return {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit,
            "run_context": {
                "execution_context": "local",
                "python_version": platform.python_version(),
                "os": platform.platform(),
            },
            "canonical_run_modes": CANONICAL_RUN_MODES,
            "core_epochs": inventory["core_epochs"],
            "metadata_epochs": inventory["metadata_epochs"],
            "strategies": inventory["strategies"],
            "verification_results": [asdict(r) for r in results],
            "drift_items": [asdict(d) for d in self.drift_items],
            "deprecation_ledger": [
                {
                    "item": "READONLY CLI alias",
                    "status": "compatibility-only",
                    "reason": "Canonical run modes are SIM/PAPER/READ_ONLY/LIVE.",
                }
            ],
            "platform_state": platform_state,
        }

    def _write_truth_artifacts(self, state: dict[str, Any], inventory: dict[str, Any], results: list[CommandResult]) -> None:
        (REPO_ROOT / "platform_integrity_state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

        repro_commands = [r.command for r in results] + ["python -m src.integrity.e23"]
        certified = [
            "# SYSTEM_STATE_CERTIFIED.md",
            "",
            f"Generated: {state['timestamp_utc']}",
            f"Platform State: **{state['platform_state']}**",
            "",
            "## Canonical Run Modes",
            "- SIM",
            "- PAPER",
            "- READ_ONLY",
            "- LIVE",
            "- Alias normalization: READONLY -> READ_ONLY (compatibility only).",
            "",
            "## Core Epoch Status (E0..E22)",
        ]
        certified.extend([f"- {k}: {v}" for k, v in inventory["core_epochs"].items()])
        certified.append("")
        certified.append("## Metadata Epoch Status (M0..M10)")
        certified.extend([f"- {k}: {v}" for k, v in inventory["metadata_epochs"].items()])
        certified.append("")
        certified.append("## Strategy Status (P01..P20)")
        certified.extend([f"- {k}: {v}" for k, v in inventory["strategies"].items()])
        certified.append("")
        certified.append("## Verification Reproduction")
        certified.extend([f"- `{cmd}`" for cmd in repro_commands])
        (REPO_ROOT / "SYSTEM_STATE_CERTIFIED.md").write_text("\n".join(certified) + "\n", encoding="utf-8")

        deprecations = [
            "# DEPRECATION_LEDGER.md",
            "",
            "## Compatibility / Superseded Entries",
            "- READONLY CLI alias -> compatibility-only; canonical mode is READ_ONLY.",
            "- Governing truth: src/config/runtime_config.py RunMode enum.",
            "- Evidence: output/audit/e23/* READ_ONLY and PAPER boot logs.",
        ]
        (REPO_ROOT / "DEPRECATION_LEDGER.md").write_text("\n".join(deprecations) + "\n", encoding="utf-8")

        report = [
            "# RECONCILIATION_REPORT.md",
            "",
            "## Drift Summary",
        ]
        if self.drift_items:
            report.extend([f"- [{d.severity}] {d.code}: {d.summary} (evidence: {d.evidence})" for d in self.drift_items])
        else:
            report.append("- No drift detected.")
        report.append("")
        report.append("## Auto-fix Actions")
        if self.fix_actions:
            report.extend([f"- {f['drift']}: {f['action']}" for f in self.fix_actions])
        else:
            report.append("- No auto-fixes required.")
        report.append("")
        report.append("## Verification Commands Executed")
        report.extend([f"- `{r.command}` (rc={r.returncode})" for r in results])
        (REPO_ROOT / "RECONCILIATION_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")

        evidence_manifest = {
            "timestamp_utc": state["timestamp_utc"],
            "commands": [asdict(r) for r in results],
            "drifts": [asdict(d) for d in self.drift_items],
            "fix_actions": self.fix_actions,
            "platform_state": state["platform_state"],
        }
        (self.audit_dir / "e23_evidence_manifest.json").write_text(
            json.dumps(evidence_manifest, indent=2) + "\n", encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="E23 platform integrity and reconciliation runner")
    parser.add_argument("--max-loops", type=int, default=5)
    args = parser.parse_args()
    runner = E23Runner(max_loops=args.max_loops)
    raise SystemExit(runner.run())


if __name__ == "__main__":
    main()
