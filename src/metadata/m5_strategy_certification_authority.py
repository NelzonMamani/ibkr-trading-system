from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.metadata.m0_canon_helpers import get_repo_root
from src.tools.verification.strategy_verification_runner import run_full_certification_v2
from src.tools.verification.verification_evidence_writer import write_m5_v2_evidence

CATALOGUE_STRATEGIES_REL = Path("TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES")
EVIDENCE_DIR_REL = Path("AUDIT_EVIDENCE/M5")
STATUS_ORDER = {
    "NOT_STARTED": 0,
    "PARTIAL": 1,
    "IMPLEMENTED_UNCERTIFIED": 2,
    "CERTIFIED_PAPER": 3,
    "CERTIFIED_LIVE": 4,
}


@dataclass(frozen=True)
class StrategyCatalogueEntry:
    strategy_id: str
    strategy_name: str
    catalogue_path: Path
    slug: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_capture(repo_root: Path, command: list[str], output_path: Path, timeout_s: int = 180) -> int:
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
        rc = completed.returncode
        rendered = [f"$ {' '.join(command)}", "", completed.stdout, completed.stderr]
    except subprocess.TimeoutExpired as exc:
        rc = 124
        rendered = [
            f"$ {' '.join(command)}",
            "",
            exc.stdout or "",
            exc.stderr or "",
            f"TIMEOUT after {timeout_s}s",
        ]
    output_path.write_text("\n".join(rendered).strip() + "\n", encoding="utf-8")
    return rc


def _load_catalogue_entries(repo_root: Path) -> list[StrategyCatalogueEntry]:
    strategies_dir = repo_root / CATALOGUE_STRATEGIES_REL
    entries: list[StrategyCatalogueEntry] = []
    for child in sorted(strategies_dir.iterdir()):
        if not child.is_dir():
            continue
        match = re.match(r"^(P\d{2})_(.+)$", child.name)
        if not match:
            continue
        strategy_id = match.group(1)
        if strategy_id < "P01" or strategy_id > "P20":
            continue
        raw_name = match.group(2)
        slug = raw_name.lower()
        entries.append(
            StrategyCatalogueEntry(
                strategy_id=strategy_id,
                strategy_name=raw_name,
                catalogue_path=child,
                slug=slug,
            )
        )
    return entries


def _main_strategy_choices(repo_root: Path) -> set[str]:
    main_path = repo_root / "src/main.py"
    text = main_path.read_text(encoding="utf-8") if main_path.exists() else ""
    match = re.search(r"choices=\[(.*?)\]", text, re.DOTALL)
    if not match:
        return set()
    return set(re.findall(r'"([a-z0-9_]+)"', match.group(1)))


def _tests_present(repo_root: Path, slug: str) -> bool:
    return (repo_root / "tests" / "strategies" / slug).exists() or (repo_root / "src" / "strategies" / slug / "tests").exists()


def _status_for(
    governance_present: bool,
    policy_present: bool,
    tests_present: bool,
    runnable_entrypoint_present: bool,
    compileall_rc: int,
    pytest_rc: int,
    sim_rc: int | None,
    paper_rc: int | None,
) -> str:
    if not any([governance_present, policy_present, tests_present, runnable_entrypoint_present]):
        return "NOT_STARTED"
    if not all([governance_present, policy_present]):
        return "PARTIAL"
    if compileall_rc != 0 or pytest_rc != 0:
        return "PARTIAL"
    if sim_rc == 0 and paper_rc == 0:
        return "CERTIFIED_PAPER"
    if sim_rc is not None or paper_rc is not None:
        return "IMPLEMENTED_UNCERTIFIED"
    if runnable_entrypoint_present and tests_present:
        return "IMPLEMENTED_UNCERTIFIED"
    if runnable_entrypoint_present or tests_present:
        return "PARTIAL"
    return "NOT_STARTED"




def _update_catalogue_system_state(repo_root: Path, matrix: list[dict[str, Any]]) -> None:
    state_path = repo_root / "TRADING_OS_MASTER_CATALOGUE" / "SYSTEM_STATE_CERTIFIED.md"
    if not state_path.exists():
        return

    lines = state_path.read_text(encoding="utf-8").splitlines()
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    updated: list[str] = []
    for line in lines:
        if line.startswith("**Last updated:**"):
            updated.append(f"**Last updated:** {now_date}")
        else:
            updated.append(line)

    section_header = "## Certified Strategy Epoch Status"
    strategy_lines = [section_header]
    matrix_by_id = {item["strategy_id"]: item for item in matrix}
    for strategy_id in sorted(matrix_by_id):
        item = matrix_by_id[strategy_id]
        strategy_lines.append(f"- {strategy_id}_{item['strategy_name']}: {item['status']}")

    notes_header = "## Verification Notes"
    if section_header in updated:
        start = updated.index(section_header)
        end = updated.index(notes_header) if notes_header in updated[start + 1 :] else len(updated)
        updated = updated[:start] + strategy_lines + [""] + updated[end:]
    else:
        if notes_header in updated:
            idx = updated.index(notes_header)
            updated = updated[:idx] + [""] + strategy_lines + [""] + updated[idx:]
        else:
            updated.extend(["", *strategy_lines])

    state_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")

def generate_strategy_certification_artifacts(repo_root: Path | None = None) -> dict[str, Any]:
    repo_root = get_repo_root(repo_root)
    evidence_dir = repo_root / EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)

    compileall_log = evidence_dir / "compileall_src.log"
    pytest_log = evidence_dir / "pytest_q.log"
    boot_logs_dir = evidence_dir / "boot"
    boot_logs_dir.mkdir(parents=True, exist_ok=True)

    compileall_rc = _run_capture(repo_root, [sys.executable, "-m", "compileall", "src"], compileall_log)
    pytest_rc = _run_capture(repo_root, [sys.executable, "-m", "pytest", "-q"], pytest_log)

    supported_choices = _main_strategy_choices(repo_root)
    entries = _load_catalogue_entries(repo_root)

    inventory: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    strategy_boot_results: dict[str, dict[str, Any]] = {}

    for entry in entries:
        sim_log = boot_logs_dir / f"{entry.slug}_sim.log"
        paper_log = boot_logs_dir / f"{entry.slug}_paper.log"
        sim_rc = _run_capture(
            repo_root,
            [sys.executable, "-m", "src.main", "--mode", "SIM", "--cycles", "1", "--strategy", entry.slug],
            sim_log,
        )
        paper_rc = _run_capture(
            repo_root,
            [sys.executable, "-m", "src.main", "--mode", "PAPER", "--cycles", "1", "--strategy", entry.slug],
            paper_log,
        )
        strategy_boot_results[entry.slug] = {
            "sim_rc": sim_rc,
            "paper_rc": paper_rc,
            "sim_log_path": str(sim_log.relative_to(repo_root)),
            "paper_log_path": str(paper_log.relative_to(repo_root)),
        }

    for entry in entries:
        governance_present = (entry.catalogue_path / "GOVERNANCE" / "STRATEGY_GOVERNANCE.md").exists()
        policy_present = (repo_root / "src" / "strategies" / entry.slug / "strategy_policy.py").exists()
        tests_present = _tests_present(repo_root, entry.slug)
        runnable_entrypoint_present = entry.slug in supported_choices

        notes: list[str] = []
        if not governance_present:
            notes.append("missing_governance")
        if not policy_present:
            notes.append("missing_policy")
        if not tests_present:
            notes.append("missing_tests")
        if not runnable_entrypoint_present:
            notes.append("not_cli_runnable")

        inventory.append(
            {
                "strategy_id": entry.strategy_id,
                "strategy_name": entry.strategy_name,
                "governance_present": governance_present,
                "policy_present": policy_present,
                "tests_present": tests_present,
                "runnable_entrypoint_present": runnable_entrypoint_present,
                "sim_rc": strategy_boot_results[entry.slug]["sim_rc"],
                "paper_rc": strategy_boot_results[entry.slug]["paper_rc"],
                "notes": ",".join(notes) if notes else "ok",
            }
        )

        strategy_sim_rc = strategy_boot_results[entry.slug]["sim_rc"]
        strategy_paper_rc = strategy_boot_results[entry.slug]["paper_rc"]
        status = _status_for(
            governance_present,
            policy_present,
            tests_present,
            runnable_entrypoint_present,
            compileall_rc,
            pytest_rc,
            strategy_sim_rc,
            strategy_paper_rc,
        )

        matrix.append(
            {
                "strategy_id": entry.strategy_id,
                "strategy_name": entry.strategy_name,
                "status": status,
                "compileall_log_path": str(compileall_log.relative_to(repo_root)),
                "pytest_log_path": str(pytest_log.relative_to(repo_root)),
                "sim_log_path": strategy_boot_results[entry.slug]["sim_log_path"],
                "paper_log_path": strategy_boot_results[entry.slug]["paper_log_path"],
                "sim_rc": strategy_sim_rc,
                "paper_rc": strategy_paper_rc,
                "last_verified_utc": _utc_now_iso(),
            }
        )

    sim_failures = sum(1 for item in strategy_boot_results.values() if item["sim_rc"] != 0)
    paper_failures = sum(1 for item in strategy_boot_results.values() if item["paper_rc"] != 0)

    summary = {
        "generated_at_utc": _utc_now_iso(),
        "compileall_rc": compileall_rc,
        "pytest_rc": pytest_rc,
        "sim_failures": sim_failures,
        "paper_failures": paper_failures,
        "strategy_count": len(entries),
        "status_counts": {
            status: sum(1 for item in matrix if item["status"] == status)
            for status in STATUS_ORDER
        },
    }

    (evidence_dir / "strategy_capability_inventory.json").write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )
    (evidence_dir / "strategy_certification_matrix.json").write_text(
        json.dumps(matrix, indent=2) + "\n", encoding="utf-8"
    )
    (evidence_dir / "strategy_certification_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    _update_catalogue_system_state(repo_root, matrix)

    return {
        "inventory_path": str((EVIDENCE_DIR_REL / "strategy_capability_inventory.json")),
        "matrix_path": str((EVIDENCE_DIR_REL / "strategy_certification_matrix.json")),
        "summary_path": str((EVIDENCE_DIR_REL / "strategy_certification_summary.json")),
        "compileall_log_path": str((EVIDENCE_DIR_REL / "compileall_src.log")),
        "pytest_log_path": str((EVIDENCE_DIR_REL / "pytest_q.log")),
        "boot_logs_dir": str((EVIDENCE_DIR_REL / "boot")),
    }


def run_strategy_certification_v2(strategy_name: str) -> dict[str, str]:
    result = run_full_certification_v2(strategy_name)
    evidence_path = write_m5_v2_evidence(strategy_name, result)

    return {
        "strategy": strategy_name,
        "verdict": result["verdict"],
        "evidence": evidence_path,
    }
