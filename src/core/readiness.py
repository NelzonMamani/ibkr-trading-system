"""Readiness checks for strategy wiring and pre-session artefacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.config.config_resolver import get_config
from src.utils.time_utils import to_ny_time, utc_now
from src.strategies.statistical_intraday_momentum.artefacts import (
    build_or_load_baseline_universe,
    build_or_load_session_readiness,
    load_distribution_store,
)


@dataclass(frozen=True)
class ReadinessReport:
    strategy_key: str
    is_pass: bool
    fail_reasons: List[str] = field(default_factory=list)
    artefacts: Dict[str, Any] = field(default_factory=dict)

    def to_text(self) -> str:
        status = "PASS" if self.is_pass else "FAIL"
        lines = [
            "[READINESS] Report",
            f"[READINESS] strategy={self.strategy_key} status={status}",
        ]
        if self.fail_reasons:
            lines.append("[READINESS] fail_reasons=" + "; ".join(self.fail_reasons))
        for key, payload in self.artefacts.items():
            lines.append(f"[READINESS] {key}: {payload}")
        return "\n".join(lines)


def run_readiness_check() -> ReadinessReport:
    strategy_key = str(get_config("STRATEGY_KEY") or "ross_momentum").strip().lower()
    now_utc = utc_now()
    ny_date = to_ny_time(now_utc).date().isoformat()
    fail_reasons: List[str] = []
    artefacts: Dict[str, Any] = {}

    if strategy_key not in {"ross_momentum", "statistical_intraday_momentum"}:
        fail_reasons.append(f"Unknown strategy key: {strategy_key}")

    if strategy_key == "statistical_intraday_momentum":
        baseline = build_or_load_baseline_universe(ny_date)
        artefacts["A1_baseline_universe"] = {
            "session_date": baseline.get("session_date"),
            "count": baseline.get("count"),
            "source": baseline.get("source"),
            "sample": baseline.get("sample"),
        }
        if not baseline.get("count"):
            fail_reasons.append("A1 baseline universe empty")

        dist_store = load_distribution_store(ny_date)
        artefacts["A2_distribution_store"] = {
            "session_date": dist_store.get("session_date"),
            "version": dist_store.get("version"),
            "source": dist_store.get("source"),
            "is_valid": dist_store.get("is_valid"),
        }
        if not dist_store.get("is_valid"):
            fail_reasons.append("A2 distribution store missing or invalid")

        readiness_state = build_or_load_session_readiness(ny_date)
        artefacts["A3_session_readiness"] = {
            "session_date": readiness_state.get("session_date"),
            "phase": readiness_state.get("phase"),
            "allowed": readiness_state.get("allowed"),
        }
        if readiness_state.get("phase") is None:
            fail_reasons.append("A3 session readiness missing phase")

    report = ReadinessReport(
        strategy_key=strategy_key,
        is_pass=not fail_reasons,
        fail_reasons=fail_reasons,
        artefacts=artefacts,
    )
    return report
