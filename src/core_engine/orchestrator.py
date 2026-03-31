"""Epoch 5 deterministic orchestrator."""

from __future__ import annotations

import argparse
from dataclasses import replace
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
from src.core.pricing.price_resolver import PriceResolutionError, resolve_entry_price
from src.core.intent import build_execution_intent
from src.core.mode_authority import resolve_mode_authority
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

_CANONICAL_PRICE_SOURCES = frozenset(
    {
        "IBKR_SNAPSHOT",
        "IBKR_SNAPSHOT_MID",
        "IBKR_STREAM",
        "IBKR_STREAM_MID",
    }
)
_MAX_CANONICAL_PRICE_MISMATCH_PCT = 0.10


def _derive_last_block_reason(risk_decisions: List[RiskDecisionRecord]) -> str:
    for decision in reversed(risk_decisions):
        if decision.block_reason:
            return decision.block_reason
        if decision.decision == "BLOCK" and decision.triggered_rules:
            return ",".join(decision.triggered_rules)
    return "NONE"


def _scanner_last_price(symbol: str, scanner_payload: dict) -> float | None:
    for key in ("focus_m", "watchlist_k", "candidates"):
        rows = scanner_payload.get(key) or []
        for row in rows:
            row_symbol = str(getattr(row, "symbol", None) if not isinstance(row, dict) else row.get("symbol") or "").upper()
            if row_symbol != symbol:
                continue
            value_raw = getattr(row, "last_price", None) if not isinstance(row, dict) else row.get("last_price")
            try:
                value = float(value_raw)
            except (TypeError, ValueError):
                return None
            return value if value > 0 else None
    return None


def _enforce_canonical_price_authority(
    *,
    symbol: str,
    mode: RunMode,
    entry_price: float,
    entry_price_source: str,
    scanner_payload: dict,
) -> tuple[bool, str]:
    if mode == RunMode.SIM:
        return True, "SIM_PRICE_AUTHORITY_BYPASS"

    if mode == RunMode.PAPER and entry_price_source in {"SCANNER_LAST_PRICE", "PREMARKET_REFERENCE"}:
        print(
            f"[PRICE][AUTHORITY_OVERRIDE] symbol={symbol} "
            f"mode=PAPER source={entry_price_source} action=ALLOW_NON_CANONICAL"
        )
        return True, "PAPER_FALLBACK_ALLOWED"

    if entry_price_source not in _CANONICAL_PRICE_SOURCES:
        return False, f"NON_CANONICAL_PRICE_SOURCE:{entry_price_source}"

    scanner_price = _scanner_last_price(symbol, scanner_payload)
    if scanner_price is None:
        return True, "CANONICAL_SOURCE_NO_SCANNER_COMPARISON"

    mismatch_ratio = abs(entry_price - scanner_price) / scanner_price if scanner_price > 0 else 0.0
    if mismatch_ratio > _MAX_CANONICAL_PRICE_MISMATCH_PCT:
        return False, (
            "PRICE_MISMATCH:"
            f"resolved={entry_price:.4f},scanner={scanner_price:.4f},"
            f"mismatch_pct={mismatch_ratio:.4f}"
        )
    return True, "CANONICAL_PRICE_OK"


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
    mode_input = mode_value or str(get_config("RUN_MODE_EFFECTIVE") or "READ_ONLY")
    execution_enabled_input = bool(get_config("EXECUTION_ENABLED_EFFECTIVE"))
    print(
        "[MODE][INPUT] "
        f"run_mode_raw={mode_input} execution_enabled_raw={get_config('EXECUTION_ENABLED')}"
    )
    mode_authority = resolve_mode_authority(mode_input, execution_enabled_input)
    print(
        "[MODE][NORMALIZED] "
        f"run_mode={mode_authority.requested_mode} execution_enabled={mode_authority.execution_enabled}"
    )
    print(
        "[MODE][AUTHORITY] "
        f"effective_mode={mode_authority.effective_mode} "
        f"trade_enabled={mode_authority.trade_enabled} "
        f"scan_only={mode_authority.scan_only} reason={mode_authority.reason}"
    )
    print(
        "[MODE][CYCLE] "
        f"requested={mode_authority.requested_mode} effective={mode_authority.effective_mode} "
        f"execution_enabled={mode_authority.execution_enabled} "
        f"trade_enabled={mode_authority.trade_enabled} scan_only={mode_authority.scan_only}"
    )
    mode = resolve_mode(mode_authority.effective_mode)
    print(f"[PRICE][MODE_POLICY] mode={mode.value} fallback_allowed={str(mode == RunMode.PAPER).lower()}")
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
    force_debug_trades = bool(get_config("FORCE_DEBUG_TRADES")) and mode == RunMode.SIM
    print(f"[DEBUG][STATE] force_debug_trades={str(force_debug_trades).lower()}")
    strategy_policy, scanner_policy = _scanner_policy_for_session(session.value)
    if force_debug_trades:
        scanner_policy = replace(
            scanner_policy,
            rvol_min=min(float(scanner_policy.rvol_min), 0.2),
            watchlist_rvol_min=min(float(scanner_policy.watchlist_rvol_min), 0.2),
            spread_max_pct=2.5 if scanner_policy.spread_max_pct is None else max(float(scanner_policy.spread_max_pct), 2.5),
        )
        print(
            "[PIPELINE][DEBUG_MODE] force_debug_trades=true mode=SIM "
            f"rvol_min={scanner_policy.rvol_min} watchlist_rvol_min={scanner_policy.watchlist_rvol_min} "
            f"spread_max_pct={scanner_policy.spread_max_pct}"
        )
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
        execution_enabled=mode_authority.trade_enabled,
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
    premarket_prep = load_canonical_premarket_prep_artifact() or {}
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
    focus_set = set(focus)
    for symbol in watchlist:
        print(
            f"[PIPELINE][WATCHLIST] symbol={symbol} "
            f"status={'IN_FOCUS' if symbol in focus_set else 'NOT_IN_FOCUS'}"
        )

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
    watchlist_set = set(watchlist)
    passed_setup = 0
    passed_trigger = 0
    generated_intents = 0
    risk_allowed = 0
    selected_by_arbitrator = 0
    executed = 0
    forced_intent_ids: set[str] = set()
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
            setup_detected = best_name not in {"NONE", ""}
            trigger_ready_now = setup_detected and best_conf >= 0.20
            if setup_detected:
                passed_setup += 1
            if trigger_ready_now:
                passed_trigger += 1
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
            print(
                f"[PIPELINE][SETUP] symbol={symbol} "
                f"passed={str(setup_detected).lower()} setup={best_name}"
            )
            print(
                f"[PIPELINE][TRIGGER] symbol={symbol} "
                f"ready={str(trigger_ready_now).lower()} "
                f"reason={'CONFIDENCE_OK' if trigger_ready_now else 'TRIGGER_NOT_READY'}"
            )

            strategy_id = "RossMomentumStrategy"
            try:
                trade_intents = build_trade_intents(
                    strategy_id,
                    symbol,
                    summary,
                    system_health_degraded=bool(data_quality_flags.get(symbol)),
                )
            except TypeError:
                # Backward compatibility for test mocks
                trade_intents = build_trade_intents(
                    strategy_id,
                    symbol,
                    summary,
                )
            try:
                entry_price, entry_price_source = resolve_entry_price(
                    symbol,
                    {
                        "scanner_payload": scanner_payload,
                        "premarket_prep": premarket_prep,
                    },
                )
            except PriceResolutionError as exc:
                if mode == RunMode.SIM:
                    entry_price = float(inputs.candles[-1].close)
                    entry_price_source = "SIM_SYNTHETIC_FALLBACK"
                    print(
                        f"[PIPELINE][PRICE_AUTHORITY_BYPASS] symbol={symbol} mode={mode.value} "
                        f"reason=PRICE_UNAVAILABLE detail={exc.reason} fallback_source={entry_price_source}"
                    )
                else:
                    print(f"[PIPELINE][BLOCK] symbol={symbol} reason=PRICE_UNAVAILABLE detail={exc.reason}")
                    print(f"[PIPELINE][INTENT] symbol={symbol} created=false reason=PRICE_UNAVAILABLE")
                    continue
            authority_ok, authority_reason = _enforce_canonical_price_authority(
                symbol=symbol,
                mode=mode,
                entry_price=entry_price,
                entry_price_source=entry_price_source,
                scanner_payload=scanner_payload,
            )
            if not authority_ok:
                print(f"[PIPELINE][BLOCK] symbol={symbol} reason=PRICE_AUTHORITY detail={authority_reason}")
                print(f"[PIPELINE][INTENT] symbol={symbol} created=false reason=PRICE_AUTHORITY")
                continue
            fallback_used = authority_reason == "PAPER_FALLBACK_ALLOWED"
            if mode == RunMode.SIM:
                print(
                    f"[PIPELINE][PRICE_AUTHORITY_BYPASS] symbol={symbol} mode={mode.value} "
                    f"reason={authority_reason} source={entry_price_source}"
                )
            if force_debug_trades and not trade_intents and setup_detected and trigger_ready_now:
                trade_intents = [
                    TradeIntentRecord(
                        symbol=symbol,
                        intent_id=f"debug-{cycle_id}-{symbol.lower()}",
                        setup_id=best_name,
                        side="LONG",
                        entry="DEBUG_FORCE_ENTRY",
                        stop="DEBUG_FORCE_STOP",
                        rationale="FORCE_DEBUG_TRADES enabled (SIM-only validation).",
                        tags=["FORCE_DEBUG_TRADE", "SIM_ONLY_VALIDATION"],
                        entry_price=entry_price,
                        entry_price_source=entry_price_source,
                        metadata={
                            "price_source": entry_price_source,
                            **(
                                {"price_authority": "NON_CANONICAL_ALLOWED_PAPER"}
                                if fallback_used
                                else {}
                            ),
                        },
                    )
                ]
                if fallback_used and "NON_LIVE_PRICE" not in trade_intents[0].tags:
                    trade_intents[0].tags.append("NON_LIVE_PRICE")
                forced_intent_ids.add(trade_intents[0].intent_id)
                print(f"[DEBUG][FORCED_PATH] intent_created symbol={symbol} intent_id={trade_intents[0].intent_id}")
                print(f"[PIPELINE][INTENT] symbol={symbol} created=true forced=true intent_id={trade_intents[0].intent_id}")
            for intent in trade_intents:
                print(f"[TRACE][cycle={cycle_id}][symbol={symbol}] stage=intent_creation intent_id={intent.intent_id}")
                if isinstance(intent, TradeIntentRecord):
                    intents.append(intent)
                else:
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
                            entry_price=entry_price,
                            entry_price_source=entry_price_source,
                            metadata={
                                "price_source": entry_price_source,
                                **(
                                    {"price_authority": "NON_CANONICAL_ALLOWED_PAPER"}
                                    if fallback_used
                                    else {}
                                ),
                            },
                        )
                    )
                if fallback_used and isinstance(intents[-1], TradeIntentRecord):
                    intents[-1].metadata.setdefault("price_source", entry_price_source)
                    intents[-1].metadata["price_authority"] = "NON_CANONICAL_ALLOWED_PAPER"
                    if "NON_LIVE_PRICE" not in intents[-1].tags:
                        intents[-1].tags.append("NON_LIVE_PRICE")
                generated_intents += 1
                print(f"[PIPELINE][INTENT] symbol={symbol} created=true forced=false intent_id={intent.intent_id}")
            if not trade_intents:
                print(f"[PIPELINE][INTENT] symbol={symbol} created=false reason=NO_STRATEGY_INTENT")
            print("[PIPELINE][INTENT_TRACE]")
            print(f"symbol={symbol}")
            print(f"setup_detected={str(setup_detected).lower()}")
            print(f"trigger_ready={str(trigger_ready_now).lower()}")
            print(f"intent_created={str(bool(trade_intents)).lower()}")

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
        risk_pass = output.decision in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"} and output.approved_quantity > 0
        if risk_pass:
            risk_allowed += 1
        print(
            f"[RISK] {output.symbol} decision={output.decision} size={output.max_position_size} "
            f"rules={output.triggered_rules} reason={output.rationale}"
        )
        print(
            "[MODE][RISK_CONTEXT] "
            f"symbol={output.symbol} mode={mode.value} "
            f"read_only_rule_applied={str('MODE_READONLY' in output.triggered_rules).lower()}"
        )
        print(
            f"[PIPELINE][RISK] symbol={output.symbol} allowed={str(risk_pass).lower()} "
            f"decision={output.decision} reason={output.block_reason or 'PASS'}"
        )
        if output.decision == "BLOCK":
            lifecycle_block_reason = output.block_reason or ",".join(output.triggered_rules) or "UNKNOWN"
            capital_constraints = ",".join(output.constraints) if output.constraints else "none"
            reason = output.block_reason or ",".join(output.triggered_rules) or "RISK_BLOCKED"
            print("[RISK][DETAIL]")
            print(f"symbol={output.symbol}")
            print("allowed=false")
            print(f"reason={reason}")
            print(f"lifecycle_block_reason={lifecycle_block_reason}")
            print(f"capital_constraints={capital_constraints}")
        if output.intent_id in forced_intent_ids and risk_pass:
            print(f"[DEBUG][FORCED_PATH] passed_risk symbol={output.symbol} intent_id={output.intent_id}")
        print(f"[TRACE][cycle={cycle_id}][symbol={output.symbol}] stage=risk approved_quantity={output.approved_quantity} capital_source={output.capital_source} available_capital={output.available_funds}")
        if output.decision == "BLOCK" and "HEALTH_CRITICAL" in output.triggered_rules:
            health_triggers.append((HealthStatus.CRITICAL, "risk_block"))

    arbitrated_decisions: List[RiskDecisionRecord] = []
    for decision in risk_decisions:
        selected = decision.decision in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"} and decision.approved_quantity > 0
        if selected:
            arbitrated_decisions.append(decision)
            selected_by_arbitrator += 1
        print(
            f"[PIPELINE][ARBITRATOR] symbol={decision.symbol} "
            f"selected={str(selected).lower()} reason={'RISK_ALLOWED' if selected else 'RISK_BLOCKED'}"
        )
        if decision.intent_id in forced_intent_ids and selected:
            print(f"[DEBUG][FORCED_PATH] selected_by_arbitrator symbol={decision.symbol} intent_id={decision.intent_id}")

    print_section("EXECUTION")
    working_orders = 0
    pending_entries = 0
    if execution_intent.scan_only:
        print("[EXECUTION] Execution stage skipped — intent scan_only.")
        execution_events = []
    else:
        execution_candidates: List[RiskDecisionRecord] = []
        blocked_candidates: List[ExecutionEvent] = []
        if not arbitrated_decisions:
            print("[PIPELINE][EXECUTION_GATE] symbol=NONE eligible=false reason=NO_INTENTS")
        for decision in arbitrated_decisions:
            execution_candidate_ready = decision.decision in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}
            eligible = (
                mode == RunMode.PAPER
                and mode_authority.trade_enabled
                and not mode_authority.scan_only
                and int(decision.approved_quantity) >= 1
                and execution_candidate_ready
            )
            print(
                "[MODE][EXECUTION_CONTEXT] "
                f"symbol={decision.symbol} mode={mode.value} trade_enabled={mode_authority.trade_enabled} "
                f"scan_only={mode_authority.scan_only} execution_allowed={eligible}"
            )
            print(
                "[PIPELINE][EXECUTION_GATE] "
                f"symbol={decision.symbol} effective_mode={mode.value} trade_enabled={mode_authority.trade_enabled} "
                f"scan_only={mode_authority.scan_only} eligible={eligible}"
            )
            if not eligible:
                reason = "EXECUTION_GATES_NOT_SATISFIED"
                print(f"[EXECUTION][BLOCK] symbol={decision.symbol} reason={reason}")
                blocked_candidates.append(
                    ExecutionEvent(
                        symbol=decision.symbol,
                        intent_id=decision.intent_id,
                        action="BLOCKED",
                        detail=f"reason={reason}",
                    )
                )
                continue
            print(
                "[EXECUTION][SUBMIT_ATTEMPT] "
                f"symbol={decision.symbol} qty={int(decision.approved_quantity)} order_type=MKT mode=PAPER"
            )
            execution_candidates.append(decision)

        execution_events = execute_intents(mode=mode, decisions=execution_candidates)
        execution_events.extend(blocked_candidates)
        for event in execution_events:
            broker_order_id = getattr(event, "broker_order_id", None)
            filled_quantity = int(getattr(event, "filled_quantity", 0) or 0)
            remaining_quantity = int(getattr(event, "remaining_quantity", 0) or 0)
            broker_status = str(getattr(event, "broker_status", "UNKNOWN") or "UNKNOWN")
            print(
                "[EXECUTION][SUBMIT_RESULT] "
                f"symbol={event.symbol} submitted={event.action == 'SUBMITTED'} "
                f"order_id={broker_order_id if broker_order_id is not None else 'MISSING'} reason={event.detail}"
            )
            if broker_order_id is not None:
                print(f"[EXECUTION][ORDER_ID_CAPTURED] symbol={event.symbol} order_id={broker_order_id}")
            print(f"[EXECUTION] {event.symbol} {event.action} ({event.detail})")
            execution_pass = event.action in {"SUBMITTED", "WOULD_PLACE"}
            if event.action == "SUBMITTED" and broker_order_id is None:
                print(
                    f"[INVARIANT][FAIL] submitted_order_without_broker_id symbol={event.symbol} intent_id={event.intent_id}"
                )
                raise RuntimeError(
                    "INVARIANT VIOLATION: submitted=True requires broker_order_id "
                    f"symbol={event.symbol} intent_id={event.intent_id}"
                )
            if event.action == "SUBMITTED":
                if execution_pass:
                    working_orders += 1
                    pending_entries += 1 if filled_quantity <= 0 else 0
                    print(
                        f"[ORDER_STATE] symbol={event.symbol} order_id={broker_order_id} "
                        "state=PENDING_SUBMISSION_ACK"
                    )
                    print(
                        f"[ORDER_STATE] symbol={event.symbol} order_id={broker_order_id} "
                        f"state=WORKING broker_status={broker_status} filled_qty={filled_quantity} remaining_qty={remaining_quantity}"
                    )
                    print(f"[LIFECYCLE] ORDER_SUBMITTED symbol={event.symbol} source=IBKR_EVENT")
                    print(f"[LIFECYCLE] ORDER_ACKNOWLEDGED symbol={event.symbol} source=IBKR_EVENT")
                if filled_quantity > 0:
                    executed += 1
                    lifecycle_event = "ENTRY_FILL"
                    print(
                        f"[EXECUTION][FILL] symbol={event.symbol} order_id={broker_order_id} "
                        f"filled_qty={filled_quantity} remaining_qty={remaining_quantity}"
                    )
                    print(
                        f"[LIFECYCLE][UPDATE] symbol={event.symbol} event={lifecycle_event} "
                        f"filled_qty={filled_quantity} source=IBKR_EVENT"
                    )
            elif execution_pass:
                working_orders += 1 if event.action == "WOULD_PLACE" else 0
            print(
                f"[PIPELINE][EXECUTION] symbol={event.symbol} "
                f"executed={str(execution_pass).lower()} action={event.action}"
            )
            if event.intent_id in forced_intent_ids and execution_pass:
                print(f"[DEBUG][FORCED_PATH] sent_to_execution symbol={event.symbol} intent_id={event.intent_id}")
    print(
        f"[LIFECYCLE][PORTFOLIO] open_positions={executed} "
        f"working_orders={working_orders} pending_entries={pending_entries}"
    )
    print(
        "[LIFECYCLE][RISK_SIGNALS] "
        f"trade_flow_active={str(executed > 0).lower()} "
        f"risk_blocks={max(0, len(risk_decisions) - risk_allowed)}"
    )

    print("[NO_TRADE_SUMMARY]")
    print(f"total_watchlist={len(watchlist_set)}")
    print(f"passed_setup={passed_setup}")
    print(f"passed_trigger={passed_trigger}")
    print(f"generated_intents={generated_intents}")
    print(f"risk_allowed={risk_allowed}")
    print(f"selected_by_arbitrator={selected_by_arbitrator}")
    print(f"executed={executed}")
    if passed_setup > 0 and passed_trigger > 0 and generated_intents == 0:
        print("[PIPELINE][ERROR] trigger_passed_but_no_intent")
    if passed_setup > 0 and passed_trigger > 0 and generated_intents > 0 and executed == 0:
        kill_switch_active = any(
            "KILL_SWITCH" in rule
            for decision in risk_decisions
            for rule in decision.triggered_rules
        )
        portfolio_exposure = sum(float(decision.order_value) for decision in risk_decisions if decision.risk_allowed)
        last_block_reason = _derive_last_block_reason(risk_decisions)
        print(
            "[PIPELINE][ERROR] no_execution_despite_valid_pipeline "
            f"risk_allowed={risk_allowed} selected_by_arbitrator={selected_by_arbitrator} "
            f"kill_switch_active={str(kill_switch_active).lower()} "
            f"portfolio_exposure={portfolio_exposure:.2f} last_block_reason={last_block_reason}"
        )
    if executed == 0:
        if generated_intents == 0:
            no_trade_reason = "no_intents_generated"
        elif risk_allowed == 0:
            no_trade_reason = "blocked_by_risk"
        elif selected_by_arbitrator == 0:
            no_trade_reason = "blocked_by_arbitrator"
        else:
            no_trade_reason = "execution_engine_not_firing"
        print(f"[PIPELINE][NO_TRADE_REASON] reason={no_trade_reason}")

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
    _emit_final_decisions(
        focus=focus,
        pattern_summaries=pattern_summaries,
        intents=intents,
        risk_decisions=risk_decisions,
        execution_events=execution_events,
    )
    return summary


def _emit_final_decisions(
    *,
    focus: List[str],
    pattern_summaries: List[PatternSummary],
    intents: List[TradeIntentRecord],
    risk_decisions: List[RiskDecisionRecord],
    execution_events: List[ExecutionEvent],
) -> None:
    pattern_by_symbol = {p.symbol: p for p in pattern_summaries}
    intent_by_symbol = {i.symbol: i for i in intents}
    risk_by_symbol = {r.symbol: r for r in risk_decisions}
    execution_by_symbol = {e.symbol: e for e in execution_events}
    for symbol in focus:
        pattern = pattern_by_symbol.get(symbol)
        intent = intent_by_symbol.get(symbol)
        risk = risk_by_symbol.get(symbol)
        execution = execution_by_symbol.get(symbol)
        pattern_name = pattern.best_setup if pattern else "NONE"
        trigger = "confirmation_gate" if intent else "NONE"
        outcome = "NO_PATTERN"
        reason = "NO_PATTERN_DETECTED"
        if pattern and pattern_name not in {"NONE", ""}:
            outcome = "PATTERN_NON_ACTIONABLE"
            reason = "TRIGGER_NOT_READY"
        if intent:
            outcome = "INTENT_CREATED"
            reason = "INTENT_CREATED"
        if risk and risk.decision not in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}:
            outcome = "RISK_BLOCKED"
            reason = risk.block_reason or "RISK_BLOCK"
        if execution:
            if execution.action == "SUBMITTED":
                if (execution.broker_order_id is not None) and int(execution.filled_quantity or 0) <= 0:
                    outcome = "ORDER_ACKNOWLEDGED"
                    reason = execution.detail
                elif int(execution.filled_quantity or 0) > 0:
                    outcome = "ENTRY_FILL"
                    reason = execution.detail
                else:
                    outcome = "ORDER_SUBMISSION_TRACKING_ERROR"
                    reason = "submitted_without_broker_order_id"
            elif execution.action == "BLOCKED":
                outcome = "ORDER_REJECTED"
                reason = execution.detail
            else:
                outcome = "EXECUTION_SKIPPED"
                reason = execution.detail
        print(
            f"[ROSS][FINAL_DECISION] symbol={symbol} pattern={pattern_name} "
            f"trigger={trigger} outcome={outcome} reason={reason}"
        )


def run_cycles(mode: str, cycles: int) -> List[CycleSummary]:
    summaries = []
    for cycle_id in range(1, cycles + 1):
        summaries.append(run_cycle(cycle_id=cycle_id, mode_value=mode))
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(description="Epoch 5 orchestrator.")
    parser.add_argument("--mode", default=None, help="SIM/READ_ONLY/PAPER/LIVE")
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()
    bootstrap_runtime()

    resolved_mode = args.mode or str(get_config("RUN_MODE_EFFECTIVE") or "READ_ONLY")
    summaries = run_cycles(mode=resolved_mode, cycles=args.cycles)
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
