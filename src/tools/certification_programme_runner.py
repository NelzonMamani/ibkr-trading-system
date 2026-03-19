from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, List, Optional

from src.metadata.m5_strategy_certification_authority import run_strategy_certification_v2

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_ROOT = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE"
STATE_FILE = CATALOGUE_ROOT / "SYSTEM_STATE_CERTIFIED.md"
CORE_DIR = CATALOGUE_ROOT / "01_CORE_EPOCHS"
METADATA_DIR = CATALOGUE_ROOT / "02_METADATA_EPOCHS"
STRATEGY_DIR = CATALOGUE_ROOT / "03_STRATEGIES"


@dataclass(frozen=True)
class EpochStatus:
    epoch_id: str
    status: str


@dataclass(frozen=True)
class Target:
    label: str
    epoch_id: str
    status: str
    path: Optional[Path]


def _load_state_lines() -> list[str]:
    if not STATE_FILE.exists():
        raise FileNotFoundError(f"Missing state file: {STATE_FILE}")
    return STATE_FILE.read_text(encoding="utf-8").splitlines()


def _parse_epoch_status(lines: Iterable[str], prefix: str) -> List[EpochStatus]:
    pattern = re.compile(rf"^- ({prefix}\d+_[A-Z0-9_]+):\s+([A-Z_]+)")
    statuses: List[EpochStatus] = []
    for line in lines:
        match = pattern.match(line.strip())
        if match:
            statuses.append(EpochStatus(epoch_id=match.group(1), status=match.group(2)))
    return statuses


def _next_uncertified(epochs: Iterable[EpochStatus]) -> Optional[EpochStatus]:
    for epoch in epochs:
        if epoch.status != "CERTIFIED":
            return epoch
    return None


def _resolve_epoch_path(epoch_id: str) -> Optional[Path]:
    for root in (CORE_DIR, METADATA_DIR):
        if not root.exists():
            continue
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and entry.name.endswith(epoch_id):
                return entry
    return None


def _list_strategy_targets() -> list[Path]:
    if not STRATEGY_DIR.exists():
        return []
    entries = [
        entry
        for entry in STRATEGY_DIR.iterdir()
        if entry.is_dir() and entry.name.startswith("P")
    ]
    return sorted(entries, key=lambda path: path.name)


def determine_next_target() -> Optional[Target]:
    lines = _load_state_lines()
    core_epochs = _parse_epoch_status(lines, "E")
    metadata_epochs = _parse_epoch_status(lines, "M")

    next_core = _next_uncertified(core_epochs)
    if next_core:
        return Target(
            label="CORE",
            epoch_id=next_core.epoch_id,
            status=next_core.status,
            path=_resolve_epoch_path(next_core.epoch_id),
        )

    next_metadata = _next_uncertified(metadata_epochs)
    if next_metadata:
        return Target(
            label="METADATA",
            epoch_id=next_metadata.epoch_id,
            status=next_metadata.status,
            path=_resolve_epoch_path(next_metadata.epoch_id),
        )

    strategies = _list_strategy_targets()
    if strategies:
        next_strategy = strategies[0]
        return Target(
            label="STRATEGY",
            epoch_id=next_strategy.name,
            status="NOT_STARTED",
            path=next_strategy,
        )

    return None


def _print_checklist() -> None:
    print("\nChecklist (per epoch):")
    print("- Create audit/00_REALITY_AUDIT.md")
    print("- Create audit/01_GAP_ANALYSIS.md")
    print("- Create audit/02_VERIFICATION_SUMMARY.md")
    print("- Capture evidence under audit/evidence/")
    print("- Update SYSTEM_CONSTITUTION_CERTIFIED.md")
    print("- Update SYSTEM_STATE_CERTIFIED.md")
    print("- Update CERTIFICATION_PROGRAMME_STATUS.md")
    print("- Run: python -m compileall src")
    print("- Run: pytest")
    print("- Run: targeted pytest for the epoch")
    print("- Run: SIM/PAPER/READ_ONLY/LIVE boot evidence where applicable")


def run_m5_v2_all_strategies() -> None:
    strategies = ["ross_momentum"]

    for strategy_name in strategies:
        result = run_strategy_certification_v2(strategy_name)
        print(f"[M5_V2] {strategy_name} → {result['verdict']}")


def main() -> None:
    print("Trading OS Certification Programme Runner")
    print(f"Repository: {REPO_ROOT}")
    print(f"State file: {STATE_FILE}")

    target = determine_next_target()
    if target is None:
        print("Next target: NONE (all epochs certified or not defined)")
        _print_checklist()
        return

    path_info = str(target.path) if target.path is not None else "UNKNOWN"
    print(
        "Next target: {label} {epoch_id} (status={status})".format(
            label=target.label,
            epoch_id=target.epoch_id,
            status=target.status,
        )
    )
    print(f"Catalogue path: {path_info}")
    _print_checklist()


if __name__ == "__main__":
    main()
