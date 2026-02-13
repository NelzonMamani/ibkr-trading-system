"""Automation runner for strategy sprint P01..P20 with E23 enforcement."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_ROOT = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "03_STRATEGIES"


class SprintMode(str, Enum):
    VERIFY_AND_PATCH = "VERIFY_AND_PATCH"
    IMPLEMENT_FROM_GOVERNANCE = "IMPLEMENT_FROM_GOVERNANCE"


@dataclass(frozen=True)
class StrategySpec:
    code: str
    folder: str
    mode: SprintMode
    policy_file: str = "strategy_policy.py"

    @property
    def config_flag(self) -> str:
        return f"{self.folder.upper()}_STRATEGY_ENABLED"


STRATEGY_SPECS: tuple[StrategySpec, ...] = (
    StrategySpec("P01", "ross_momentum", SprintMode.VERIFY_AND_PATCH),
    StrategySpec("P02", "statistical_intraday_momentum", SprintMode.VERIFY_AND_PATCH),
    StrategySpec("P03", "mean_reversion", SprintMode.VERIFY_AND_PATCH, policy_file="mean_reversion_strategy_policy.py"),
    StrategySpec("P04", "long_horizon_value", SprintMode.VERIFY_AND_PATCH),
    StrategySpec("P05", "opening_drive", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P06", "vwap_reclaim", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P07", "power_hour", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P08", "volatility_expansion", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P09", "range_bound_fade", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P10", "support_resistance_channel", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P11", "event_earnings_reaction", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P12", "event_news_shock_continuation", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P13", "volatility_contraction_breakout", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P14", "volatility_carry_risk_premium", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P15", "pairs_divergence_reversion", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P16", "cross_sectional_relative_strength_rotation", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P17", "time_based_seasonality", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P18", "trend_following_classic", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P19", "long_horizon_quality_compounder", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
    StrategySpec("P20", "regime_adaptive_meta_allocator", SprintMode.IMPLEMENT_FROM_GOVERNANCE),
)


class StrategySprintRunner:
    def __init__(self) -> None:
        self.registry_path = REPO_ROOT / "src" / "integrity" / "epoch_verification_registry.yaml"
        self.strategy_registry_path = REPO_ROOT / "src" / "strategies" / "strategy_registry.py"
        self.config_registry_path = REPO_ROOT / "src" / "config" / "config_registry.py"

    def run(self, start: str = "P01", end: str = "P20") -> None:
        selected = list(self._slice_specs(start, end))
        if not selected:
            raise ValueError("No strategy specs selected for the requested range")

        for spec in selected:
            self._verify_structure(spec)
            self._verify_wiring(spec)
            self._verify_config_toggle(spec)
            self._verify_risk_hook(spec)
            self._verify_tests(spec)
            self._run_strategy_checks(spec)
            self._run_e23(spec)

    def _slice_specs(self, start: str, end: str) -> Iterable[StrategySpec]:
        codes = [s.code for s in STRATEGY_SPECS]
        if start not in codes or end not in codes:
            raise ValueError(f"Invalid range: {start}..{end}")
        i = codes.index(start)
        j = codes.index(end)
        if i > j:
            raise ValueError("--from must be <= --to")
        return STRATEGY_SPECS[i : j + 1]

    def _run_cmd(self, cmd: list[str]) -> None:
        subprocess.run(cmd, cwd=REPO_ROOT, check=True)

    def _verify_structure(self, spec: StrategySpec) -> None:
        strategy_dir = REPO_ROOT / "src" / "strategies" / spec.folder
        if not strategy_dir.is_dir():
            raise RuntimeError(f"{spec.code}: missing strategy folder {strategy_dir}")
        policy_path = strategy_dir / spec.policy_file
        if not policy_path.is_file():
            raise RuntimeError(f"{spec.code}: missing policy file {policy_path}")
        catalog_prefix = f"{spec.code}_"
        matches = list(CATALOG_ROOT.glob(f"{catalog_prefix}*"))
        if not matches:
            raise RuntimeError(f"{spec.code}: missing governance catalogue folder under {CATALOG_ROOT}")

    def _verify_wiring(self, spec: StrategySpec) -> None:
        contents = self.strategy_registry_path.read_text(encoding="utf-8")
        if spec.folder not in contents:
            print(f"[SPRINT][WARN] {spec.code}: strategy id '{spec.folder}' not found in strategy_registry.py")

    def _verify_config_toggle(self, spec: StrategySpec) -> None:
        contents = self.config_registry_path.read_text(encoding="utf-8")
        if spec.config_flag not in contents:
            raise RuntimeError(f"{spec.code}: missing config toggle {spec.config_flag}")

    def _verify_risk_hook(self, spec: StrategySpec) -> None:
        strategy_dir = REPO_ROOT / "src" / "strategies" / spec.folder
        merged = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in strategy_dir.glob("*.py"))
        tokens = ("risk", "position", "sizing", "limit")
        if not any(token in merged.lower() for token in tokens):
            print(f"[SPRINT][WARN] {spec.code}: no obvious risk hook tokens found in {strategy_dir}")

    def _verify_tests(self, spec: StrategySpec) -> None:
        tests_dir = REPO_ROOT / "src" / "strategies" / spec.folder / "tests"
        if not tests_dir.is_dir():
            raise RuntimeError(f"{spec.code}: missing strategy-local tests at {tests_dir}")

    def _run_strategy_checks(self, spec: StrategySpec) -> None:
        tests_dir = REPO_ROOT / "src" / "strategies" / spec.folder / "tests"
        self._run_cmd(["pytest", "-q", str(tests_dir)])

    def _run_e23(self, spec: StrategySpec) -> None:
        self._run_cmd(["python", "-m", "src.integrity.e23"])
        state_path = REPO_ROOT / "platform_integrity_state.json"
        state = state_path.read_text(encoding="utf-8")
        if '"platform_state": "DRIFT_DETECTED"' in state or '"platform_state": "INVARIANT_VIOLATION"' in state:
            raise RuntimeError(f"{spec.code}: E23 reported non-coherent platform_state")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P01..P20 strategy sprint with E23 after each strategy")
    parser.add_argument("--from", dest="start", default="P01")
    parser.add_argument("--to", dest="end", default="P20")
    args = parser.parse_args()
    StrategySprintRunner().run(start=args.start, end=args.end)


if __name__ == "__main__":
    main()
