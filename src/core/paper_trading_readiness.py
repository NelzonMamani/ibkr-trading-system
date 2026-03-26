from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

from src.config.config_resolver import get_config, set_config_overrides
from src.config.runtime_config import resolve_ibkr_connection
from src.events import event_types
from src.scanner.scanner_runner import GateThresholds, _evaluate_focus_gates
from src.scanner.session_pct_change import (
    compute_phase_aware_rvol,
    compute_session_aligned_pct_change,
)


@dataclass
class PaperReadinessReport:
    is_pass: bool
    checks_passed: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = [
            "[PAPER_READINESS] report",
            f"[PAPER_READINESS] status={'PASS' if self.is_pass else 'FAIL'}",
        ]
        for item in self.checks_passed:
            lines.append(f"[PAPER_READINESS][PASS] {item}")
        for item in self.failures:
            lines.append(f"[PAPER_READINESS][FAIL] {item}")
        lines.append(
            "[PAPER_READINESS][PIPELINE] scan -> watchlist -> focus -> setup -> trigger -> intent -> order -> fill -> position"
        )
        return "\n".join(lines)


def run_paper_trading_readiness_check(
    *,
    ensure_connection: bool = True,
    connection_probe: Callable[[], None] | None = None,
) -> PaperReadinessReport:
    """Run pre-paper-trading safety and capability checks.

    This validator is intentionally fail-fast: any critical misconfiguration marks FAIL.
    """

    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})

    passed: List[str] = []
    failures: List[str] = []

    # Part 1 — execution enablement
    run_mode = str(get_config("RUN_MODE_EFFECTIVE") or "")
    execution_effective = bool(get_config("EXECUTION_ENABLED_EFFECTIVE"))
    readonly = bool(get_config("IBKR_READONLY_ENABLED"))
    if run_mode != "PAPER":
        failures.append(f"RUN_MODE_EFFECTIVE must be PAPER (got {run_mode})")
    else:
        passed.append("RUN_MODE_EFFECTIVE=PAPER")
    if not execution_effective:
        failures.append("EXECUTION_ENABLED_EFFECTIVE must be True in paper validation")
    else:
        passed.append("EXECUTION_ENABLED_EFFECTIVE=True")

    # Part 2 — lifecycle wiring signals present
    required_events = [
        "ORDER_SUBMISSION_ATTEMPTED",
        "ORDER_SUBMITTED_ACK",
        "ORDER_FILL_RECORDED",
        "TRADE_OPENED",
        "TRADE_CLOSED",
    ]
    missing = [name for name in required_events if not hasattr(event_types, name)]
    if missing:
        failures.append(f"Missing lifecycle event contracts: {missing}")
    else:
        passed.append("TradeIntent->Order->Fill->Position event contracts present")

    # Part 3 — IBKR connectivity fail-fast
    try:
        _, port, _, _ = resolve_ibkr_connection()
    except Exception as exc:
        failures.append(f"IBKR connection config invalid: {exc}")
    else:
        if port != 7497:
            failures.append(f"Paper mode requires port 7497 (got {port})")
        else:
            passed.append("IBKR paper port validated (7497)")

    if readonly:
        failures.append("IBKR_READONLY_ENABLED is True; paper execution would be blocked")
    else:
        passed.append("IBKR read-only guard disabled for paper execution")

    if ensure_connection:
        try:
            if connection_probe is not None:
                connection_probe()
            else:
                from src.adapters.brokers.ibkr.ibkr_connection_manager import (
                    get_shared_ibkr_connection_manager,
                )

                manager = get_shared_ibkr_connection_manager()
                manager.ensure_connected()
                manager.disconnect(reason="paper_readiness_probe")
            passed.append("IBKR TWS/Gateway connection probe succeeded")
        except Exception as exc:
            failures.append(f"IBKR TWS/Gateway connection probe failed: {exc}")

    # Part 4 — session-aware metric validation
    pct = compute_session_aligned_pct_change(
        session_label="PRE",
        cur_last=12.0,
        ref_close_rth=10.0,
        rth_open_price=11.0,
        rth_close_price=10.0,
        ibkr_change_pct=None,
    )
    if pct.final_pct != 20.0:
        failures.append(f"session pct_change validation failed (expected 20.0, got {pct.final_pct})")
    else:
        passed.append("Session-aligned pct_change check passed")

    rvol = compute_phase_aware_rvol(
        session_label="RTH_OPEN",
        session_volume=40000.0,
        avg_volume_20d=100000.0,
    )
    if rvol.rvol_phase != 1.0:
        failures.append(f"phase-aware RVOL validation failed (expected 1.0, got {rvol.rvol_phase})")
    else:
        passed.append("Phase-aware RVOL check passed")

    pre_min = int(get_config("PREMARKET_MIN_VOLUME"))
    rth_min = int(get_config("RTH_MIN_VOLUME"))
    if pre_min >= rth_min:
        failures.append(
            f"Phase-aware volume thresholds invalid: PREMARKET_MIN_VOLUME={pre_min} must be < RTH_MIN_VOLUME={rth_min}"
        )
    else:
        passed.append("Phase-aware volume thresholds validated")

    # Part 5 — safety filters (spread/liquidity/halt/SSR)
    thresholds = GateThresholds(
        min_price=1.0,
        max_price=100.0,
        min_pct_change=5.0,
        max_pct_change=None,
        watchlist_rvol_min=1.0,
        focus_rvol_min=2.0,
        focus_volume_min=10_000,
        focus_volume_min_early_rth=5_000,
        focus_volume_min_early_rth_ratio=0.4,
        min_volume=10_000,
        min_premarket_volume=2_000,
        max_float=20_000_000,
        spread_max_pct=0.03,
        min_dollar_volume=100_000,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=False,
        allow_unknown_float=True,
    )
    high_spread_context = {
        "session": "RTH_OPEN",
        "symbol": "TEST",
        "last_price": 10.0,
        "volume": 50_000,
        "dollar_volume": 500_000,
        "spread_pct": 0.5,
        "halted": False,
        "ssr": False,
        "rvol": 3.0,
        "rvol_discovery": 3.0,
        "rvol_phase": 3.0,
        "pct_change": 12.0,
    }
    halted_context = {
        "session": "RTH_OPEN",
        "symbol": "TEST",
        "last_price": 10.0,
        "volume": 50_000,
        "dollar_volume": 500_000,
        "spread_pct": 0.01,
        "halted": True,
        "ssr": False,
        "rvol": 3.0,
        "rvol_discovery": 3.0,
        "rvol_phase": 3.0,
        "pct_change": 12.0,
    }
    ssr_context = dict(halted_context, halted=False, ssr=True)
    if _evaluate_focus_gates(high_spread_context, thresholds) != "DROP_SPREAD":
        failures.append("Spread max threshold safety gate failed to enforce")
    elif _evaluate_focus_gates(halted_context, thresholds) != "DROP_HALTED":
        failures.append("Halt protection failed")
    elif _evaluate_focus_gates(ssr_context, thresholds) != "DROP_SSR":
        failures.append("SSR protection failed")
    else:
        passed.append("Spread/Halt/SSR protections enforced")

    return PaperReadinessReport(is_pass=not failures, checks_passed=passed, failures=failures)
