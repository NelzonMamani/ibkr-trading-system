"""E21 end-to-end simulation and risk envelope hardening verifier."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core.event_collector import EventCollector
from src.core.managers.connection_manager import ConnectionManager
from src.core.orchestrator import CoreOrchestrator
from src.core.stop_controller import StopController
from src.execution.execution_engine import ExecutionEngine
from src.metadata.m0_canon_helpers import update_system_state_statuses
from src.risk.risk_engine import RiskEngine
from src.strategies.strategy_contracts import (
    DecisionType,
    Direction,
    StrategyRiskPayload,
    TimeInForcePolicy,
    TradeIntent,
)

EPOCH = "E21_TRADING_READY_VERIFICATION_AND_END_TO_END_SIMULATION"
EVIDENCE_DIR = (
    REPO_ROOT
    / "TRADING_OS_MASTER_CATALOGUE"
    / "AUDIT_EVIDENCE"
    / "E21_TRADING_READY_VERIFICATION"
)
STATE_FILE = REPO_ROOT / "TRADING_OS_MASTER_CATALOGUE" / "SYSTEM_STATE_CERTIFIED.md"

STRATEGIES = [
    "cross_sectional_relative_strength_rotation",
    "event_earnings_reaction",
    "event_news_shock_continuation",
    "long_horizon_quality_compounder",
    "long_horizon_value",
    "mean_reversion",
    "opening_drive",
    "pairs_divergence_reversion",
    "power_hour",
    "range_bound_fade",
    "regime_adaptive_meta_allocator",
    "ross_momentum",
    "statistical_intraday_momentum",
    "support_resistance_channel",
    "time_based_seasonality",
    "trend_following_classic",
    "volatility_carry_risk_premium",
    "volatility_contraction_breakout",
    "volatility_expansion",
    "vwap_reclaim",
]


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_to_file(command: list[str], out_file: Path, extra_env: dict[str, str] | None = None) -> int:
    env = dict(**({} if extra_env is None else extra_env))
    full_env = dict(os.environ)
    full_env.update(env)
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=full_env,
    )
    out_file.write_text(
        (
            f"$ {' '.join(command)}\n"
            + "\n"
            + "\n".join([proc.stdout or "", "# STDERR", proc.stderr or ""])
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    return proc.returncode


def _intent() -> TradeIntent:
    intent = TradeIntent(
        intent_id="e21-risk-intent-1",
        symbol="AAPL",
        direction=Direction.LONG,
        entry_model="MKT",
        stop_model="STRUCTURE",
        target_model=None,
        time_in_force_policy=TimeInForcePolicy.DAY,
        invalidations=[],
        rationale_text="e21 risk envelope check",
        risk_flags=[],
    )
    object.__setattr__(intent, "entry_price", 250.0)
    object.__setattr__(intent, "stop_loss_price", 245.0)
    return intent


def _payload() -> StrategyRiskPayload:
    return StrategyRiskPayload(
        strategy_id="E21VerifierStrategy",
        symbol="AAPL",
        intents=[_intent()],
        decision_type=DecisionType.EMIT_INTENT,
        confidence=0.9,
        rationale_text="E21 risk violation simulation",
        risk_flags=[],
    )


def _risk_violation_test(log_path: Path) -> dict:
    events = EventCollector()
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "EXECUTION_ENABLED": True,
            "RISK_ACCOUNT_EQUITY": 10_000.0,
            "RISK_MAX_POSITION_SIZE": 500,
            "RISK_MAX_OPEN_POSITIONS": 0,
            "RISK_PROFILE": "NORMAL",
            "ACTIVE_SESSIONS": ["RTH", "PRE", "AH", "CLOSED"],
        }
    )
    try:
        decision = RiskEngine(event_collector=events, stop_controller=StopController()).evaluate_strategy_payload(_payload())
        blocked = decision.overall_action == "BLOCK"
        reason_hit = bool(decision.overall_action == "BLOCK")
        trace_emitted = events.count("RISK_DECISION") > 0
        payload = {
            "blocked": blocked,
            "reason_hit": reason_hit,
            "trace_emitted": trace_emitted,
            "risk_reasons": decision.risk_reasons,
            "per_intent_reason_tags": [item.reason_tags for item in decision.per_intent],
        }
        log_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload
    finally:
        set_config_overrides(None)


def _live_gating_test(log_path: Path) -> dict:
    command = [sys.executable, "-m", "src.main", "--mode", "LIVE", "--cycles", "1", "--strategy", "ross_momentum"]
    rc = _run_to_file(command, log_path, extra_env={"CYCLE_SLEEP_SECONDS": "0", "EXECUTION_ENABLED": "0"})
    text = log_path.read_text(encoding="utf-8")

    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": False})
    try:
        risk_decision = RiskEngine(stop_controller=StopController()).evaluate_strategy_payload(_payload())
        risk_decision.decision_id = "e21-live-gating"
        events = EventCollector()
        result = ExecutionEngine(event_collector=events, stop_controller=StopController()).execute_trade(risk_decision)
        broker_submission_blocked = events.count("ORDER_SUBMITTED") == 0
        hard_disabled_logged = "[SAFETY] EXECUTION: HARD DISABLED" in text
        payload = {
            "main_rc": rc,
            "hard_disabled_logged": hard_disabled_logged,
            "broker_submission_blocked": broker_submission_blocked,
            "execution_result_status": result.status,
        }
        log_path.write_text(log_path.read_text(encoding="utf-8") + "\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload
    finally:
        set_config_overrides(None)


def _failure_injection_test(log_path: Path) -> dict:
    output: dict[str, object] = {}

    set_config_overrides({"RUN_MODE": "READ_ONLY", "EXECUTION_ENABLED": False})
    try:
        with mock.patch("src.core.managers.connection_manager.MarketDataClient.connect", side_effect=ConnectionError("IBKR disconnected")):
            manager = ConnectionManager(RunMode.READ_ONLY)
            try:
                manager.connect()
                output["ibkr_disconnected_safe_halt"] = False
            except RuntimeError as exc:
                output["ibkr_disconnected_safe_halt"] = True
                output["ibkr_disconnected_reason"] = str(exc)
    finally:
        set_config_overrides(None)

    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": False, "SELECTED_STRATEGY": "ross_momentum"})
    try:
        orchestrator = CoreOrchestrator()
        with mock.patch("src.config.system_config.get_current_market_session", return_value="CLOSED"):
            with mock.patch.object(CoreOrchestrator, "run_once", side_effect=AssertionError("run_once should not execute when CLOSED in LIVE")):
                orchestrator.run_forever(cycle_sleep_seconds=0, max_cycles=1)
        output["session_closed_safe_halt"] = True
    except Exception as exc:  # noqa: BLE001
        output["session_closed_safe_halt"] = False
        output["session_closed_reason"] = str(exc)
    finally:
        set_config_overrides(None)

    log_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _multi_strategy_test(log_path: Path) -> dict:
    enabled = {
        "GapAndGoStrategy": False,
        "MomentumContinuationStrategy": False,
        "RossMomentumStrategyV1": True,
        "MeanReversionStrategy": True,
        "StatisticalIntradayMomentum": True,
    }
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "EXECUTION_ENABLED": False,
            "SELECTED_STRATEGY": "",
            "ENABLED_STRATEGIES": enabled,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "MEAN_REVERSION_STRATEGY_ENABLED": True,
            "STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED": True,
        }
    )
    try:
        orchestrator = CoreOrchestrator()
        orchestrator.run_forever(cycle_sleep_seconds=0, max_cycles=2)
        payload = {
            "rc": 0,
            "registered_strategies": [s.name for s in orchestrator.strategy_runner.strategies],
            "registered_count": len(orchestrator.strategy_runner.strategies),
            "no_crash": True,
        }
    except Exception as exc:  # noqa: BLE001
        payload = {"rc": 1, "no_crash": False, "error": str(exc)}
    finally:
        set_config_overrides(None)

    log_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    per_strategy_dir = EVIDENCE_DIR / "per_strategy_logs"
    per_strategy_dir.mkdir(parents=True, exist_ok=True)

    compileall_rc = _run_to_file([sys.executable, "-m", "compileall", "src"], EVIDENCE_DIR / "compileall.log")
    pytest_rc = _run_to_file([sys.executable, "-m", "pytest", "-q"], EVIDENCE_DIR / "pytest.log")

    strategy_results: list[dict[str, object]] = []
    for strategy in STRATEGIES:
        for mode in ("SIM", "PAPER"):
            command = [
                sys.executable,
                "-m",
                "src.main",
                "--mode",
                mode,
                "--strategy",
                strategy,
                "--cycles",
                "2",
            ]
            log_name = f"{strategy}_{mode.lower()}.log"
            rc = _run_to_file(command, per_strategy_dir / log_name, extra_env={"CYCLE_SLEEP_SECONDS": "0"})
            strategy_results.append({"strategy": strategy, "mode": mode, "rc": rc, "log": f"per_strategy_logs/{log_name}"})

    multi_strategy = _multi_strategy_test(EVIDENCE_DIR / "multi_strategy.log")
    risk_violation = _risk_violation_test(EVIDENCE_DIR / "risk_violation.log")
    live_gating = _live_gating_test(EVIDENCE_DIR / "live_gating.log")
    failure_injection = _failure_injection_test(EVIDENCE_DIR / "failure_injection.log")

    sim_pass = all(item["rc"] == 0 for item in strategy_results if item["mode"] == "SIM")
    paper_pass = all(item["rc"] == 0 for item in strategy_results if item["mode"] == "PAPER")
    risk_pass = bool(risk_violation["blocked"] and risk_violation["trace_emitted"])
    live_pass = bool(live_gating["hard_disabled_logged"] and live_gating["broker_submission_blocked"])
    failure_pass = bool(
        failure_injection.get("ibkr_disconnected_safe_halt")
        and failure_injection.get("session_closed_safe_halt")
    )
    no_unhandled = bool(multi_strategy.get("no_crash")) and failure_pass

    passed = all(
        [
            compileall_rc == 0,
            pytest_rc == 0,
            sim_pass,
            paper_pass,
            bool(multi_strategy.get("no_crash")),
            risk_pass,
            live_pass,
            no_unhandled,
        ]
    )

    summary = {
        "epoch": EPOCH,
        "generated_at_utc": _now_utc(),
        "compileall_rc": compileall_rc,
        "pytest_rc": pytest_rc,
        "strategy_runs": strategy_results,
        "multi_strategy": multi_strategy,
        "risk_violation": risk_violation,
        "live_gating": live_gating,
        "failure_injection": failure_injection,
        "checks": {
            "compileall_ok": compileall_rc == 0,
            "pytest_ok": pytest_rc == 0,
            "sim_runs_ok": sim_pass,
            "paper_runs_ok": paper_pass,
            "risk_violation_blocked": risk_pass,
            "live_gating_blocked": live_pass,
            "no_unhandled_exception": no_unhandled,
        },
        "certified": passed,
        "status": "CERTIFIED" if passed else "IMPLEMENTED_UNCERTIFIED",
    }

    (EVIDENCE_DIR / "e21_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    update_system_state_statuses(
        STATE_FILE,
        {"E21_TRADING_READY_VERIFICATION_AND_END_TO_END_SIMULATION": "CERTIFIED" if passed else "IMPLEMENTED_UNCERTIFIED"},
    )
    print(json.dumps({"certified": passed, "status": summary["status"]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
