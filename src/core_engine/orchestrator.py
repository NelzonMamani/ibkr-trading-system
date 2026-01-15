"""Deterministic orchestrator for Epoch 5."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from typing import Dict, List

from src.config.config_resolver import set_config_overrides
from src.config.system_config import get_current_market_session
from src.core_engine.health import evaluate_health
from src.core_engine.state import CycleSummary, ScannerArtifact
from src.execution.order_router import route_orders
from src.risk.risk_engine import Epoch5RiskEngine
from src.scanner.scanner_runner import run_scanner_cycle
from src.storage.trade_store import TradeStore
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.decision_policy import build_trade_intents
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext, TradeIntent
from src.utils.logging import normalize_mode_label, print_section
from src.utils.time_utils import CycleIdGenerator


def _apply_mode_overrides(mode_label: str) -> str:
    normalized = normalize_mode_label(mode_label)
    overrides: Dict[str, object]
    if normalized == "READONLY":
        overrides = {
            "RUN_MODE": "LIVE_READ_ONLY",
            "EXECUTION_ENABLED": False,
            "IBKR_API_WRITE_ALLOWED": False,
            "IBKR_READONLY_ENABLED": True,
        }
    elif normalized == "LIVE_1SHARE":
        overrides = {
            "RUN_MODE": "LIVE_MICRO",
            "EXECUTION_ENABLED": True,
            "IBKR_API_WRITE_ALLOWED": True,
            "IBKR_READONLY_ENABLED": False,
        }
    else:
        overrides = {
            "RUN_MODE": "SIM",
            "EXECUTION_ENABLED": False,
            "IBKR_API_WRITE_ALLOWED": False,
            "IBKR_READONLY_ENABLED": True,
        }
    set_config_overrides(overrides)
    return normalized


def _scanner_artifact_from_payload(payload: Dict[str, object]) -> ScannerArtifact:
    return ScannerArtifact(
        topn_count=int(payload.get("topn_count", len(payload.get("symbols", [])))),
        survivors_count=int(payload.get("survivors_count", len(payload.get("watchlist", [])))),
        watchlist=list(payload.get("watchlist", [])),
        focus=[row.symbol for row in payload.get("focus_rows", [])],
        drop_summary=dict(payload.get("drop_ledger_summary", {})),
    )


def _session_context(session_label: str) -> SessionContext:
    if session_label == "PRE":
        return SessionContext.PRE
    if session_label in {"REGULAR", "REG"}:
        return SessionContext.REGULAR
    if session_label == "AFTER":
        return SessionContext.AFTER
    return SessionContext.REGULAR


def _build_pattern_inputs(symbol: str, session: SessionContext, cycle_id: int) -> PatternInputs:
    base = 10.0 + (sum(ord(char) for char in symbol) % 10) * 0.1 + cycle_id * 0.01
    candles = [
        Candle(open=base, high=base + 0.15, low=base - 0.05, close=base + 0.1, volume=1200),
        Candle(open=base + 0.1, high=base + 0.25, low=base + 0.05, close=base + 0.2, volume=1400),
        Candle(open=base + 0.2, high=base + 0.35, low=base + 0.15, close=base + 0.3, volume=1600),
        Candle(open=base + 0.3, high=base + 0.32, low=base + 0.22, close=base + 0.25, volume=900),
        Candle(open=base + 0.25, high=base + 0.45, low=base + 0.2, close=base + 0.4, volume=1800),
    ]
    indicators = IndicatorSet(ema9=base + 0.2, ema20=base + 0.15, vwap=base + 0.18)
    levels = LevelSet(premarket_high=base + 0.3, hod=base + 0.45, prior_close=base - 0.2)
    liquidity = LiquidityContext(spread=0.02, float_millions=12.0, rvol=2.0)
    return PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=candles,
        session_context=session,
        levels=levels,
        indicators=indicators,
        liquidity_context=liquidity,
        data_quality_flags=[],
    )


def run_cycles(mode: str, cycles: int) -> List[CycleSummary]:
    resolved_mode = _apply_mode_overrides(mode)
    cycle_ids = CycleIdGenerator()
    summaries: List[CycleSummary] = []
    evaluator = PatternEvaluator()
    risk_engine = Epoch5RiskEngine()
    store = TradeStore()

    for _ in range(cycles):
        cycle_id = cycle_ids.next_id()
        session = get_current_market_session()
        session_context = _session_context(session)
        print_section(f"CYCLE {cycle_id} MODE={resolved_mode} SESSION={session}")

        health_snapshot = None
        scanner_payload = run_scanner_cycle(mode="orchestrator")
        scanner_artifact = _scanner_artifact_from_payload(scanner_payload)
        print(
            "Scanner: "
            f"TopN={scanner_artifact.topn_count} "
            f"Survivors={scanner_artifact.survivors_count} "
            f"K={len(scanner_artifact.watchlist)} "
            f"M={len(scanner_artifact.focus)}"
        )
        print(f"WATCHLIST_K: {scanner_artifact.watchlist}")
        print(f"FOCUS_M: {scanner_artifact.focus}")
        all_pattern_results: List[object] = []
        if not scanner_artifact.focus:
            print("[ORCHESTRATOR] EMPTY FOCUS_M (valid) — skipping downstream stages")
            intents: List[TradeIntent] = []
            risk_decisions = []
            execution_events = []
        else:
            print("[DATA] Hydrating PatternInputs for FocusM symbols")
            pattern_inputs = [
                _build_pattern_inputs(symbol, session_context, cycle_id)
                for symbol in scanner_artifact.focus
            ]
            data_quality_flags: List[str] = []
            for inputs in pattern_inputs:
                data_quality_flags.extend(inputs.data_quality_flags)
            pattern_summaries = []
            for inputs in pattern_inputs:
                summary = evaluator.evaluate([inputs])
                pattern_summaries.append(summary)
                all_pattern_results.extend(summary.all_results)
                if summary.best_long_setup:
                    print(
                        "[PATTERNS] "
                        f"{inputs.symbol} best={summary.best_long_setup.pattern_name} "
                        f"conf={summary.best_long_setup.confidence:.2f}"
                    )
                else:
                    print(f"[PATTERNS] {inputs.symbol} best=none")

            intents = []
            for inputs, summary in zip(pattern_inputs, pattern_summaries):
                intents.extend(
                    build_trade_intents(
                        strategy_id="RossMomentum",
                        symbol=inputs.symbol,
                        summary=summary,
                        session=inputs.session_context,
                    )
                )

            if intents:
                print(f"[STRATEGY] intents={len(intents)}")
                for intent in intents:
                    print(
                        "[STRATEGY][INTENT] "
                        f"symbol={intent.symbol} setup={intent.intent_id} "
                        f"side={intent.direction.value}"
                    )
            else:
                print("[STRATEGY] 0 intents")

            critical_reasons: List[str] = []
            if data_quality_flags and resolved_mode == "LIVE_1SHARE":
                critical_reasons.append("DATA_QUALITY")
            health_snapshot = evaluate_health(
                storage_ok=True,
                data_quality_flags=data_quality_flags,
                critical_reasons=critical_reasons,
            )
            risk_decisions = risk_engine.evaluate_intents(
                intents,
                mode_label=resolved_mode,
                health_status=health_snapshot.status.value,
            )
            if health_snapshot.status.value == "CRITICAL":
                execution_events = []
                print("[EXECUTION] CRITICAL health — execution blocked")
            else:
                execution_events = route_orders(intents, risk_decisions, resolved_mode)

        storage_ok = True
        try:
            store.persist_cycle(
                cycle_id,
                {
                    "scanner": scanner_artifact,
                    "pattern_results": all_pattern_results if scanner_artifact.focus else [],
                    "intents": intents,
                    "risk_decisions": risk_decisions,
                    "execution_events": execution_events,
                    "session": session,
                    "mode": resolved_mode,
                },
            )
        except Exception as exc:
            storage_ok = False
            print(f"[STORAGE] ERROR {exc}")

        post_critical: List[str] = []
        if not storage_ok and resolved_mode == "LIVE_1SHARE":
            post_critical.append("STORAGE_FAILURE")
        if health_snapshot is None:
            health_snapshot = evaluate_health(
                storage_ok=storage_ok,
                critical_reasons=post_critical or None,
            )
        elif not storage_ok:
            health_snapshot = evaluate_health(
                storage_ok=storage_ok,
                data_quality_flags=health_snapshot.reasons,
                critical_reasons=post_critical or None,
            )
        summary = CycleSummary(
            cycle_id=cycle_id,
            mode=resolved_mode,
            session=session,
            scanner=scanner_artifact,
            intents_count=len(intents),
            risk_decisions=len(risk_decisions),
            execution_actions=len(execution_events),
            storage_ok=storage_ok,
            health_status=health_snapshot.status.value,
            health_reasons=health_snapshot.reasons,
        )
        summaries.append(summary)
        print(f"[CYCLE_SUMMARY] {asdict(summary)}")
        print(f"[HEALTH] {health_snapshot.status.value} reasons={health_snapshot.reasons}")
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(description="Epoch 5 deterministic orchestrator")
    parser.add_argument("--mode", default="READONLY", help="SIM/READONLY/LIVE_1SHARE")
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()

    cycles = max(1, args.cycles)
    run_cycles(args.mode, cycles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
