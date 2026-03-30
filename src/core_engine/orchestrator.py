"""Epoch 5 deterministic orchestrator."""

from __future__ import annotations

import argparse
from typing import List
from zoneinfo import ZoneInfo

from src.config.config_resolver import get_config
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
from src.core_engine.state import CycleContext, RunMode, resolve_session_state
from src.core.intent import build_execution_intent
from src.execution.order_router import execute_intents
from src.prep.premarket_prep_artifact import write_premarket_prep_artifact
from src.prep.premarket_prep import PreMarketPrepEngine
from src.prep.premarket_prep_artifact import (
    CANONICAL_PREP_ARTIFACT_PATH,
    load_canonical_premarket_prep_artifact,
    write_canonical_premarket_prep_artifact,
)
from src.risk.risk_audit import AccountSnapshot, evaluate_trade_intents
from src.utils.capital_resolver import resolve_available_capital
from src.runtime.bootstrap import bootstrap_runtime
from src.scanner.contracts import StockSelectionPolicy
from src.scanner.scanner_contract import scanner_request_from_policy
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
    UniverseSource,
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


def _resolve_live_available_funds(mode) -> AccountSnapshot:
    if str(getattr(mode, "value", mode)).upper() != "LIVE":
        return AccountSnapshot(
            available_funds=float(get_config("RISK_ACCOUNT_EQUITY")),
            source="CONFIG",
            canonical=False,
            broker_connection_state="NON_LIVE",
        )

    try:
        from src.adapters.brokers.ibkr.ibkr_connection_manager import (
            get_shared_ibkr_connection_manager,
        )

        manager = get_shared_ibkr_connection_manager(readonly_enabled=False)
        client = manager.get_client()
        metadata = manager.connection_metadata()
        print(
            "[CAPITAL][IBKR][MANAGER] "
            f"connected_client_id={metadata.get('connected_client_id')} "
            f"generation={metadata.get('connection_generation')}"
        )
        available = float(resolve_available_capital(client, allow_fallback=False))
        return AccountSnapshot(
            available_funds=available,
            source="IBKR_CANONICAL",
            canonical=True,
            broker_connection_state="CONNECTED",
        )
    except Exception as exc:
        print(f"[CAPITAL][IBKR][BLOCK] source=UNAVAILABLE reason={exc}")
        return AccountSnapshot(
            available_funds=0.0,
            source="UNAVAILABLE",
            canonical=False,
            broker_connection_state="DEGRADED",
        )



_prep_engine = PreMarketPrepEngine(event_collector=None)


def _ensure_deterministic_prep() -> None:
    existing = load_canonical_premarket_prep_artifact()
    if existing:
        restored = _prep_engine.hydrate_from_artifact(existing.get("symbols") or [])
        print(f"[PREP] hydrate ok path={CANONICAL_PREP_ARTIFACT_PATH} restored_symbols={restored}")
        return

    symbols_raw = get_config("SCANNER_SYMBOLS") or []
    fallback_raw = get_config("SCANNER_DEFAULT_SYMBOLS") or []
    symbols = [str(symbol).upper() for symbol in symbols_raw if str(symbol).strip()]
    symbols.extend(str(symbol).upper() for symbol in fallback_raw if str(symbol).strip())
    symbols.extend(["AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN", "SMCI", "PLTR", "RIVN"])
    ordered = []
    seen = set()
    for symbol in symbols:
        if symbol in seen:
            continue
        seen.add(symbol)
        ordered.append(symbol)
    symbols = ordered[:30]
    if len(symbols) < 10:
        symbols.extend([f"SYM{i}" for i in range(1, 11 - len(symbols))])
    print(f"[PREP] mode=CLOSED prepared_symbols={len(symbols)}")
    placeholder = {
        "timestamp": utc_now().isoformat(),
        "symbols": [
            {
                "symbol": symbol,
                "premarket_high": None,
                "premarket_low": None,
                "gap": None,
                "float": None,
                "news_context": [],
            }
            for symbol in symbols
        ],
    }
    try:
        out_path = write_canonical_premarket_prep_artifact(placeholder)
        print(f"[PREP] placeholder artifact written path={out_path}")
    except Exception as exc:
        print(f"[PREP][ERROR] {exc} continuing")


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


def _scanner_policy_for_session(session: str) -> tuple[RossMomentumPolicy, StockSelectionPolicy]:
    strategy_policy = RossMomentumPolicy()
    stock_policy = stock_selection_policy_for_session_phase(
        strategy_policy,
        _policy_session_phase(session),
    )
    return strategy_policy, stock_policy


def _scanner_request_for_policy(
    stock_policy: StockSelectionPolicy,
    *,
    strategy_name: str,
    session_phase: str,
):
    override_symbols = None
    if stock_policy.universe.source == UniverseSource.CONFIG_SYMBOLS:
        override_symbols = get_config("SCANNER_SYMBOLS")
    return scanner_request_from_policy(
        stock_policy,
        optional_symbols_override=override_symbols,
        strategy_name=strategy_name,
        session_phase=session_phase,
    )


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


def run_cycle(
    cycle_id: int,
    mode_value: str,
    forced_session_state=None,
) -> CycleSummary:
    _ensure_deterministic_prep()
    mode = resolve_mode(mode_value)
    resolved_session = resolve_session_state()
    session = forced_session_state or resolved_session
    now = utc_now()
    context = CycleContext(
        cycle_id=cycle_id,
        mode=mode,
        session=session,
        timestamp=now.isoformat(),
    )

    ny_now = now.astimezone(ZoneInfo("America/New_York"))
    utc_stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(
        "[SESSION] "
        f"utc={utc_stamp} "
        f"ny={ny_now.strftime('%H:%M:%S')} "
        f"resolved={resolved_session.value} "
        f"forced={forced_session_state.value if forced_session_state else 'none'} "
        f"used={session.value}"
    )
    print_section(f"CYCLE {cycle_id} MODE={mode.value} SESSION={session.value}")
    print(f"[TRACE][cycle={cycle_id}] stage=cycle_start mode={mode.value} session={session.value}")
    strategy_policy, scanner_policy = _scanner_policy_for_session(session.value)
    scanner_request = _scanner_request_for_policy(
        scanner_policy,
        strategy_name="ross_momentum",
        session_phase=_policy_session_phase(session),
    )
    execution_intent = build_execution_intent(
        strategy_name=strategy_policy.name,
        mode=mode.value,
        session_phase=session.value,
        policy=scanner_policy,
        execution_enabled=True,
    )
    print(
        "[ORCH][POLICY] loaded strategy=ross_momentum "
        f"version={strategy_policy.version} policy={strategy_policy.name} "
        "stock_selection=ENABLED"
    )
    print(
        "[ORCH][POLICY] delegating to scanner "
        f"watchlist_k={scanner_policy.watchlist_limit_k} "
        f"focus_m={scanner_policy.focus_limit_m} "
        f"top_n={scanner_policy.top_gainers_n}"
    )
    print(
        "[ORCH][POLICY] scanner_universe="
        f"{scanner_request.universe_source.value} "
        f"scan_code={scanner_request.ibkr_scan_code} "
        f"top_n={scanner_request.requested_top_n}"
    )
    print(
        "[INTENT] "
        f"strategy={execution_intent.strategy_name} "
        f"mode={execution_intent.mode} "
        f"session_phase={execution_intent.session_phase} "
        f"trade_enabled={execution_intent.trade_enabled} "
        f"scan_only={execution_intent.scan_only} "
        f"enforcement={execution_intent.enforcement}"
    )
    scanner_kwargs = {
        "mode": mode.value,
        "policy": scanner_policy,
        "scanner_request": scanner_request,
    }
    if forced_session_state is not None:
        scanner_kwargs["forced_session_label"] = session.value
        scanner_kwargs["forced_session_source"] = "TEST_OVERRIDE"
    scanner_payload = run_scanner_cycle(**scanner_kwargs)
    watchlist = scanner_payload.get("watchlist_k_symbols", [])
    focus = scanner_payload.get("focus_m_symbols", [])
    if not watchlist:
        watchlist = scanner_payload.get("watchlist", [])
    if not watchlist:
        watchlist = [
            getattr(candidate, "symbol", None) or candidate.get("symbol")
            for candidate in scanner_payload.get("watchlist_k", [])
            if isinstance(candidate, dict) or hasattr(candidate, "symbol")
        ]
        watchlist = [symbol for symbol in watchlist if symbol]
    if not focus:
        focus = [
            getattr(candidate, "symbol", None) or candidate.get("symbol")
            for candidate in scanner_payload.get("focus_m", [])
            if isinstance(candidate, dict) or hasattr(candidate, "symbol")
        ]
        focus = [symbol for symbol in focus if symbol]
    drop_summary = scanner_payload.get("drop_reason_summary", {})
    print(
        f"Scanner: TopN={scanner_payload.get('topn_count', len(scanner_payload.get('symbols', [])))} "
        f"Survivors={scanner_payload.get('survivors_count', len(watchlist))} "
        f"K={len(watchlist)} M={len(focus)}"
    )
    print_watchlist_focus(watchlist, focus, drop_summary)
    print(f"[TRACE][cycle={cycle_id}] stage=focus_list_finalisation focus_count={len(focus)}")

    if session.value in {"PRE", "AFTER"}:
        write_premarket_prep_artifact(
            mode=mode.value,
            session=session.value,
            scanner_payload=scanner_payload,
            watchlist_k=scanner_policy.watchlist_limit_k,
        )

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
                print(f"[TRACE][cycle={cycle_id}][symbol={symbol}] stage=intent_creation intent_id={intent.intent_id}")
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
                        entry_price=float(getattr(intent, "entry_price", 1.0) or 1.0),
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
    account = _resolve_live_available_funds(mode)
    risk_outputs = evaluate_trade_intents(
        intents=intents,
        mode=mode,
        health_status=health_status,
        account=account,
    )
    for output in risk_outputs:
        risk_decisions.append(output)
        print(
            f"[RISK] {output.symbol} decision={output.decision} size={output.max_position_size} "
            f"rules={output.triggered_rules} reason={output.rationale}"
        )
        print(f"[TRACE][cycle={cycle_id}][symbol={output.symbol}] stage=risk approved_quantity={output.approved_quantity} capital_source={output.capital_source} available_capital={output.available_funds}")
        if output.decision == "BLOCK" and "HEALTH_CRITICAL" in output.triggered_rules:
            health_triggers.append((HealthStatus.CRITICAL, "risk_block"))

    print_section("EXECUTION")
    if execution_intent.scan_only:
        print("[EXECUTION] Execution stage skipped — intent scan_only.")
        execution_events = []
    else:
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
    if not storage_ok and mode.value == "LIVE":
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
    parser.add_argument("--mode", default="READ_ONLY", help="SIM/READ_ONLY/PAPER/LIVE")
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()
    bootstrap_runtime()

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
