"""Epoch 5 deterministic orchestrator."""

from __future__ import annotations

import argparse
from typing import List

from src.core_engine.bootstrap import resolve_mode
from src.core_engine.events import (
    CycleSummary,
    ExecutionEvent,
    PatternSummary,
    RiskDecisionRecord,
    ScannerArtifact,
    TradeIntentRecord,
)
from src.core_engine.health import HealthStatus, combine_health
from src.core_engine.state import CycleContext, resolve_session_state
from src.execution.order_router import execute_intents
from src.risk.risk_audit import evaluate_trade_intents
from src.scanner.contracts import StockSelectionPolicy
from src.scanner.scanner_runner import run_scanner_cycle
from src.storage.trade_store import TradeStore
from src.strategies.ross_momentum.decision_policy import build_trade_intents
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluator
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.strategy_contracts import SessionContext
from src.strategies.ross_momentum.strategy_policy import (
    RossMomentumPolicy,
    stock_selection_policy_for_session_phase,
)
from src.utils.logging import print_section, print_watchlist_focus
from src.utils.time_utils import utc_now
from src.utils.validation import asdict_safe


STAGE_ORDER = [
    "Scanner",
    "Data",
    "Patterns",
    "Strategy",
    "Risk",
    "Execution",
    "Storage",
    "Health",
]


def _session_context(session: str) -> SessionContext:
    if session == "PRE":
        return SessionContext.PRE
    if session == "REG":
        return SessionContext.REGULAR
    return SessionContext.AFTER


def _policy_session_phase(session: str) -> str:
    if session == "PRE":
        return "PREMARKET"
    if session == "REG":
        return "MORNING"
    return "LATE"


def _scanner_policy_for_session(
    session: str,
    strategy_policy: RossMomentumPolicy | None = None,
) -> tuple[RossMomentumPolicy, StockSelectionPolicy]:
    strategy_policy = strategy_policy or RossMomentumPolicy()
    stock_policy = stock_selection_policy_for_session_phase(
        strategy_policy,
        _policy_session_phase(session),
    )
    scanner_policy = StockSelectionPolicy(
        policy_name=strategy_policy.name,
        universe_source=stock_policy.universe_source,
        exchange_allowlist=stock_policy.exchange_allowlist,
        top_gainers_n=stock_policy.top_gainers_n,
        watchlist_limit_k=stock_policy.watchlist_limit_k,
        focus_limit_m=stock_policy.focus_limit_m,
        price_min=stock_policy.price_min,
        price_max=stock_policy.price_max,
        gap_min_pct=stock_policy.gap_min_pct,
        rvol_min=stock_policy.rvol_min,
        float_max_millions=stock_policy.float_max_millions,
        min_volume=stock_policy.min_volume,
        min_premarket_volume=stock_policy.min_premarket_volume,
        spread_max_pct=stock_policy.spread_max_pct,
        require_catalyst=stock_policy.require_catalyst,
        allow_halts=stock_policy.allow_halts,
        allow_ssr=stock_policy.allow_ssr,
        data_quality_require_price=stock_policy.data_quality_require_price,
        data_quality_require_bid_ask=stock_policy.data_quality_require_bid_ask,
        max_symbols_per_cycle=stock_policy.max_symbols_per_cycle,
        session_allowlist=stock_policy.session_allowlist,
    )
    return strategy_policy, scanner_policy


def _build_synthetic_inputs(
    symbol: str, data_quality_flags: List[str], session: str
) -> PatternInputs:
    base = sum(ord(ch) for ch in symbol) % 10
    prices = [10 + base + idx * 0.2 for idx in range(8)]
    candles = []
    for idx, price in enumerate(prices):
        open_price = price
        close_price = price + (0.05 if idx % 2 == 0 else -0.03)
        high = max(open_price, close_price) + 0.02
        low = min(open_price, close_price) - 0.02
        candles.append(
            Candle(
                open=open_price,
                high=high,
                low=low,
                close=close_price,
                volume=1000 + idx * 50,
            )
        )
    indicators = IndicatorSet(ema9=prices[-1] - 0.1, ema20=prices[-1] - 0.15, vwap=prices[-1] - 0.05)
    levels = LevelSet(
        premarket_high=prices[-2] + 0.05,
        hod=prices[-1] + 0.2,
        prior_close=prices[0] - 0.1,
    )
    liquidity = LiquidityContext(spread=0.02, float_millions=15.0, rvol=2.5)
    return PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=candles,  # type: ignore[arg-type]
        session_context=_session_context(session),
        levels=levels,
        indicators=indicators,
        liquidity_context=liquidity,
        data_quality_flags=data_quality_flags,
    )


def run_cycle(cycle_id: int, mode_value: str) -> CycleSummary:
    mode = resolve_mode(mode_value)
    session = resolve_session_state()
    now = utc_now()
    context = CycleContext(
        cycle_id=cycle_id,
        mode=mode,
        session=session,
        timestamp=now.isoformat(),
    )

    print_section(f"CYCLE {cycle_id} MODE={mode.value} SESSION={session.value}")
    strategy_policy, scanner_policy = _scanner_policy_for_session(session.value)
    print(
        f"[ORCH][POLICY] loaded strategy=ross_momentum version={strategy_policy.version} "
        f"policy={strategy_policy.name} stock_selection=ENABLED (mechanical policy)"
    )
    print(
        "[ORCH][POLICY] delegating to scanner "
        f"watchlist_k={scanner_policy.watchlist_limit_k} "
        f"focus_m={scanner_policy.focus_limit_m} "
        f"top_n={scanner_policy.top_gainers_n}"
    )
    scanner_payload = run_scanner_cycle(mode=mode.value, policy=scanner_policy)
    watchlist = scanner_payload.get("watchlist_k", scanner_payload.get("watchlist", []))
    focus = scanner_payload.get("focus_m", [])
    drop_summary = scanner_payload.get("drop_reason_summary", {})
    print(
        f"Scanner: TopN={scanner_payload.get('topn_count', len(scanner_payload.get('symbols', [])))} "
        f"Survivors={scanner_payload.get('survivors_count', len(watchlist))} "
        f"K={len(watchlist)} M={len(focus)}"
    )
    print_watchlist_focus(watchlist, focus, drop_summary)

    scanner_artifact = ScannerArtifact(
        context=context,
        topn_count=int(scanner_payload.get("topn_count", len(scanner_payload.get("symbols", [])))),
        survivors_count=int(scanner_payload.get("survivors_count", len(watchlist))),
        watchlist_k=watchlist,
        focus_m=focus,
        drop_reason_summary=drop_summary,
        new_symbols=scanner_payload.get("new_symbols", []),
        continuing_symbols=scanner_payload.get("continuing_symbols", []),
        dropped_symbols=scanner_payload.get("dropped_symbols", []),
        raw_payload=scanner_payload,
    )

    pattern_summaries: List[PatternSummary] = []
    intents: List[TradeIntentRecord] = []
    risk_decisions: List[RiskDecisionRecord] = []
    execution_events: List[ExecutionEvent] = []
    health_triggers = []
    data_quality_flags = scanner_payload.get("data_quality_by_symbol", {})
    if any(data_quality_flags.values()):
        health_triggers.append((HealthStatus.DEGRADED, "data_quality"))

    if not focus:
        print_section("DATA")
        print("No focus symbols; skipping data hydration.")
        print_section("PATTERNS")
        print("No focus symbols; skipping pattern evaluation.")
    else:
        print_section("DATA")
        print(f"Hydrating data for focus symbols: {focus}")
        print_section("PATTERNS")
        evaluator = PatternEvaluator()
        for symbol in focus:
            data_quality = scanner_payload.get("data_quality_by_symbol", {}).get(symbol, [])
            inputs = _build_synthetic_inputs(symbol, data_quality, session.value)
            summary = evaluator.evaluate([inputs])
            best_setup = summary.best_long_setup or summary.best_short_setup
            best_name = best_setup.pattern_name if best_setup else "NONE"
            best_conf = best_setup.confidence if best_setup else 0.0
            rationale = summary.combined_rationale_text
            pattern_summaries.append(
                PatternSummary(
                    symbol=symbol,
                    best_setup=best_name,
                    confidence=best_conf,
                    rationale=rationale,
                    all_patterns=[asdict_safe(result) for result in summary.all_results],
                )
            )
            print(f"[PATTERN] {symbol} best={best_name} conf={best_conf:.2f}")

            strategy_id = "RossMomentumStrategy"
            trade_intents = build_trade_intents(strategy_id, symbol, summary)
            for intent in trade_intents:
                combined_tags = list(intent.risk_flags)
                if data_quality:
                    combined_tags.append("DATA_QUALITY")
                intents.append(
                    TradeIntentRecord(
                        symbol=symbol,
                        intent_id=intent.intent_id,
                        setup_id=best_name,
                        side=intent.direction.value,
                        entry=intent.entry_model,
                        stop=intent.stop_model,
                        rationale=intent.rationale_text,
                        tags=combined_tags,
                    )
                )

    print_section("STRATEGY")
    if intents:
        for intent in intents:
            print(
                f"[INTENT] {intent.symbol} setup={intent.setup_id} side={intent.side} "
                f"entry={intent.entry} stop={intent.stop} rationale={intent.rationale}"
            )
    else:
        print("[INTENT] 0 intents generated.")

    print_section("RISK")
    health_status = None
    if health_triggers:
        health_status = combine_health(health_triggers).status
    risk_outputs = evaluate_trade_intents(
        intents=intents,
        mode=mode,
        health_status=health_status,
    )
    for output in risk_outputs:
        risk_decisions.append(output)
        print(
            f"[RISK] {output.symbol} decision={output.decision} size={output.max_position_size} "
            f"rules={output.triggered_rules} reason={output.rationale}"
        )
        if output.decision == "BLOCK" and "HEALTH_CRITICAL" in output.triggered_rules:
            health_triggers.append((HealthStatus.CRITICAL, "risk_block"))

    print_section("EXECUTION")
    execution_events = execute_intents(mode=mode, decisions=risk_decisions)
    for event in execution_events:
        print(f"[EXECUTION] {event.symbol} {event.action} ({event.detail})")

    store = TradeStore()
    storage_ok = store.persist_cycle(
        scanner=scanner_artifact,
        patterns=pattern_summaries,
        intents=intents,
        risk_decisions=risk_decisions,
        executions=execution_events,
    )
    print_section("STORAGE")
    print("Storage: OK" if storage_ok else "Storage: FAIL")
    if not storage_ok and mode.value == "LIVE_1SHARE":
        health_triggers.append((HealthStatus.CRITICAL, "storage_failure"))
    elif not storage_ok:
        health_triggers.append((HealthStatus.DEGRADED, "storage_failure"))

    health_snapshot = combine_health(health_triggers)
    print_section("HEALTH")
    print(f"Health: {health_snapshot.summary()}")

    summary = CycleSummary(
        context=context,
        scanner=scanner_artifact,
        pattern_summaries=pattern_summaries,
        intents=intents,
        risk_decisions=risk_decisions,
        execution_events=execution_events,
        health=health_snapshot,
        stage_order=STAGE_ORDER,
    )
    return summary


def run_cycles(mode: str, cycles: int) -> List[CycleSummary]:
    summaries = []
    for cycle_id in range(1, cycles + 1):
        summaries.append(run_cycle(cycle_id=cycle_id, mode_value=mode))
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(description="Epoch 5 orchestrator.")
    parser.add_argument("--mode", default="READONLY", help="SIM/READONLY/LIVE_1SHARE")
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()

    summaries = run_cycles(mode=args.mode, cycles=args.cycles)
    print_section("CYCLE SUMMARY")
    for summary in summaries:
        print(
            f"CYCLE {summary.context.cycle_id} "
            f"health={summary.health.status.value} "
            f"intents={len(summary.intents)} "
            f"decisions={len(summary.risk_decisions)} "
            f"executions={len(summary.execution_events)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
