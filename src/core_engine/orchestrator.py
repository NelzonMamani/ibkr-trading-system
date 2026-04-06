"""Epoch 5 deterministic orchestrator."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, replace
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
from src.execution.order_router import execute_intents, fill_authority_state, runtime_lifecycle_snapshot
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

TERMINAL_STATES = {
    "NO_SETUP": "NO_SETUP",
    "SETUP_NO_TRIGGER": "SETUP_NO_TRIGGER",
    "TRIGGER_READY": "TRIGGER_READY",
    "TRIGGER_BLOCKED_BY_POLICY": "TRIGGER_BLOCKED_BY_POLICY",
    "INTENT_EMITTED": "INTENT_EMITTED",
    "BLOCKED_BY_RISK": "BLOCKED_BY_RISK",
    "BLOCKED_BY_EXECUTION_PRECHECK": "BLOCKED_BY_EXECUTION_PRECHECK",
    "ORDER_SUBMITTED": "ORDER_SUBMITTED",
    "ORDER_REJECTED": "ORDER_REJECTED",
}

PIPELINE_BLOCKER_TAXONOMY = {
    "SCANNER_DROP",
    "WATCHLIST_EXCLUDED",
    "FOCUS_EXCLUDED",
    "NO_SETUP_DETECTED",
    "SETUP_DETECTED_TRIGGER_NOT_FIRED",
    "TRIGGER_FIRED_NO_INTENT",
    "INTENT_BLOCKED_BY_RISK",
    "INTENT_NOT_ROUTED_TO_EXECUTION",
    "EXECUTION_PRECHECK_FAIL",
    "IBKR_SUBMISSION_FAIL",
    "ORDER_ACK_MISSING",
    "FILL_PENDING",
    "OTHER_UNCLASSIFIED",
}

_CANONICAL_PRICE_SOURCES = frozenset(
    {
        "IBKR_SNAPSHOT",
        "IBKR_SNAPSHOT_MID",
        "IBKR_STREAM",
        "IBKR_STREAM_MID",
    }
)
_MAX_CANONICAL_PRICE_MISMATCH_PCT = 0.10


@dataclass(frozen=True)
class PriceAuthorityVerdict:
    allowed: bool
    reason: str
    normalized_source: str
    reason_code: str


def _normalize_price_source_label(source: str) -> str:
    normalized = str(source or "").strip().upper()
    if not normalized:
        return "UNKNOWN"
    if normalized in _CANONICAL_PRICE_SOURCES:
        return normalized
    if normalized.startswith("IBKR_"):
        if "MID" in normalized:
            if "STREAM" in normalized or "L1" in normalized:
                return "IBKR_STREAM_MID"
            return "IBKR_SNAPSHOT_MID"
        if "STREAM" in normalized or "L1" in normalized:
            return "IBKR_STREAM"
        if "SNAPSHOT" in normalized or "MARKET_DATA" in normalized:
            return "IBKR_SNAPSHOT"
    if normalized == "PREMARKET_PREP":
        return "PREP_REFERENCE_PRICE"
    if normalized == "PREMARKET_PREP_ARTIFACT":
        return "PREP_REFERENCE_PRICE"
    return normalized


def _diagnose_ibkr_snapshot_unavailability(*, symbol: str, scanner_payload: dict) -> str:
    diagnostics = scanner_payload.get("diagnostics") if isinstance(scanner_payload, dict) else None
    market_diag = diagnostics.get("market_snapshot_enrichment") if isinstance(diagnostics, dict) else None
    if not isinstance(market_diag, dict):
        print(f"[PRICE][IBKR_MISSING] symbol={symbol} reason=SESSION_OR_DATA_TIMING")
        return "SESSION_OR_DATA_TIMING"
    if not market_diag.get("requested", True):
        print(f"[PRICE][IBKR_MISSING] symbol={symbol} reason=IBKR_SNAPSHOT_UNAVAILABLE")
        return "IBKR_SNAPSHOT_UNAVAILABLE"
    if int(market_diag.get("snapshot_failure_count") or 0) > 0 and int(market_diag.get("snapshot_success_count") or 0) == 0:
        print(f"[PRICE][IBKR_MISSING] symbol={symbol} reason=IBKR_SNAPSHOT_UNAVAILABLE")
        return "IBKR_SNAPSHOT_UNAVAILABLE"
    if int(market_diag.get("symbols_with_last_price") or 0) == 0:
        print(f"[PRICE][IBKR_MISSING] symbol={symbol} reason=IBKR_SNAPSHOT_INCOMPLETE")
        return "IBKR_SNAPSHOT_INCOMPLETE"
    print(f"[PRICE][IBKR_MISSING] symbol={symbol} reason=IBKR_SNAPSHOT_STALE")
    return "IBKR_SNAPSHOT_STALE"


def _derive_last_block_reason(risk_decisions: List[RiskDecisionRecord]) -> str:
    for decision in reversed(risk_decisions):
        if decision.block_reason:
            return decision.block_reason
        if decision.decision == "BLOCK" and decision.triggered_rules:
            return ",".join(decision.triggered_rules)
    return "NONE"


def _pipeline_stage_log(
    *,
    stage: str,
    symbol: str,
    strategy: str,
    mode: str,
    session: str,
    outcome: str,
    reason_code: str,
) -> None:
    print(
        f"[PIPELINE][{stage}] symbol={symbol} strategy={strategy} mode={mode} "
        f"session={session} outcome={outcome} reason_code={reason_code}"
    )


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
    session: str,
    entry_price: float,
    entry_price_source: str,
    scanner_payload: dict,
) -> PriceAuthorityVerdict:
    normalized_source = _normalize_price_source_label(entry_price_source)
    if mode in {RunMode.PAPER, RunMode.LIVE}:
        if normalized_source not in _CANONICAL_PRICE_SOURCES:
            print(f"[PRICE][AUTHORITY_VIOLATION] symbol={symbol} mode={mode.value} source={normalized_source} action=BLOCK")
            return PriceAuthorityVerdict(
                allowed=False,
                reason=f"NO_IBKR_PRICE_AUTHORITY:{normalized_source}",
                normalized_source=normalized_source,
                reason_code=f"NO_IBKR_PRICE_AUTHORITY:{normalized_source}",
            )

        scanner_price = _scanner_last_price(symbol, scanner_payload)
        if scanner_price is None:
            return PriceAuthorityVerdict(
                allowed=True,
                reason="CANONICAL_SOURCE_NO_SCANNER_COMPARISON",
                normalized_source=normalized_source,
                reason_code="CANONICAL_SOURCE_NO_SCANNER_COMPARISON",
            )

        mismatch_ratio = abs(entry_price - scanner_price) / scanner_price if scanner_price > 0 else 0.0
        if mismatch_ratio > _MAX_CANONICAL_PRICE_MISMATCH_PCT:
            return PriceAuthorityVerdict(
                allowed=False,
                reason=(
                    "PRICE_MISMATCH:"
                    f"resolved={entry_price:.4f},scanner={scanner_price:.4f},"
                    f"mismatch_pct={mismatch_ratio:.4f}"
                ),
                normalized_source=normalized_source,
                reason_code="IBKR_SNAPSHOT_STALE",
            )
        return PriceAuthorityVerdict(
            allowed=True,
            reason="CANONICAL_PRICE_OK",
            normalized_source=normalized_source,
            reason_code="CANONICAL_PRICE_OK",
        )

    if mode == RunMode.SIM:
        return PriceAuthorityVerdict(
            allowed=True,
            reason="SIM_MODE_BYPASS",
            normalized_source=normalized_source,
            reason_code="SIM_MODE_BYPASS",
        )

    return PriceAuthorityVerdict(
        allowed=False,
        reason=f"NO_IBKR_PRICE_AUTHORITY:{normalized_source}",
        normalized_source=normalized_source,
        reason_code=f"NO_IBKR_PRICE_AUTHORITY:{normalized_source}",
    )


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
    requested_mode = mode_authority.requested_mode
    if requested_mode == "PAPER":
        execution_enabled_cfg = bool(get_config("EXECUTION_ENABLED"))
        submission_enabled_cfg = bool(get_config("IBKR_ORDER_SUBMISSION_ENABLED"))
        readonly_enabled_cfg = bool(get_config("IBKR_READONLY_ENABLED"))

        # Determine if execution is actually intended.
        execution_requested = execution_enabled_cfg or submission_enabled_cfg

        # Only enforce invariant if execution is requested.
        if execution_requested:
            if (not execution_enabled_cfg) or (not submission_enabled_cfg) or readonly_enabled_cfg:
                print("[PIPELINE][FATAL] execution_disabled_misconfig")
                raise RuntimeError("[PIPELINE][FATAL] execution_disabled_misconfig")
    resolved_session = resolve_session_state()
    session = forced_session_state or resolved_session
    if (
        mode_authority.requested_mode == "PAPER"
        and session.value == "AFTER"
        and (
            mode_authority.effective_mode != "PAPER"
            or not mode_authority.trade_enabled
            or mode_authority.scan_only
        )
    ):
        mode_authority = replace(
            mode_authority,
            effective_mode="PAPER",
            trade_enabled=True,
            scan_only=False,
            reason="paper_after_hours_override",
        )
        print("[MODE][OVERRIDE] preserving PAPER mode during AFTER_HOURS for lifecycle validation")
        print("[MODE][FORCE] PAPER mode enforced during AFTER_HOURS")
    mode = resolve_mode(mode_authority.effective_mode)
    print(f"[PRICE][MODE_POLICY] mode={mode.value} fallback_allowed={str(mode == RunMode.PAPER).lower()}")
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
    strategy_name = str(strategy_policy.name or "ROSS_MOMENTUM")
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
    scanned_symbols = [
        str(symbol).upper()
        for symbol in (scanner_payload.get("symbols") or scanner_payload.get("top_n_symbols") or [])
        if symbol
    ]
    dropped_symbols = scanner_payload.get("dropped_symbols") or []
    dropped_by_symbol: dict[str, str] = {}
    for dropped in dropped_symbols:
        if isinstance(dropped, dict):
            dropped_symbol = str(dropped.get("symbol") or "").upper()
            dropped_reason = str(dropped.get("drop_reason") or dropped.get("reason") or "SCANNER_DROP")
        else:
            dropped_symbol = str(dropped or "").upper()
            dropped_reason = "SCANNER_DROP"
        if dropped_symbol:
            dropped_by_symbol.setdefault(dropped_symbol, dropped_reason)
    first_blocker_by_symbol: dict[str, str] = {}
    first_blocker_reason_by_symbol: dict[str, str] = {}

    for symbol, reason in dropped_by_symbol.items():
        first_blocker_by_symbol[symbol] = "SCANNER_DROP"
        first_blocker_reason_by_symbol[symbol] = reason
        _pipeline_stage_log(
            stage="SCAN_RESULT",
            symbol=symbol,
            strategy=strategy_name,
            mode=mode.value,
            session=session.value,
            outcome="DROP",
            reason_code=reason,
        )

    watchlist_set_for_scan = {str(symbol).upper() for symbol in watchlist}
    for symbol in scanned_symbols:
        normalized_symbol = str(symbol).upper()
        if normalized_symbol in dropped_by_symbol:
            continue
        in_watchlist = normalized_symbol in watchlist_set_for_scan
        _pipeline_stage_log(
            stage="SCAN_RESULT",
            symbol=normalized_symbol,
            strategy=strategy_name,
            mode=mode.value,
            session=session.value,
            outcome="PASS" if in_watchlist else "DROP",
            reason_code="SCANNER_PASS" if in_watchlist else "SCANNER_NOT_SELECTED",
        )
        if not in_watchlist and normalized_symbol not in first_blocker_by_symbol:
            first_blocker_by_symbol[normalized_symbol] = "WATCHLIST_EXCLUDED"
            first_blocker_reason_by_symbol[normalized_symbol] = "SCANNER_NOT_SELECTED"
    print(
        f"Scanner: TopN={scanner_payload.get('topn_count', len(scanner_payload.get('symbols', [])))} "
        f"Survivors={scanner_payload.get('survivors_count', len(watchlist))} "
        f"K={len(watchlist)} M={len(focus)}"
    )
    print_watchlist_focus(watchlist, focus, drop_summary)
    print(f"[TRACE][cycle={cycle_id}] stage=focus_list_finalisation focus_count={len(focus)}")
    focus_set = set(focus)
    for symbol in watchlist:
        _pipeline_stage_log(
            stage="WATCHLIST",
            symbol=symbol,
            strategy=strategy_name,
            mode=mode.value,
            session=session.value,
            outcome="INCLUDED",
            reason_code="WATCHLIST_PASS",
        )
        print(
            f"[PIPELINE][WATCHLIST] symbol={symbol} "
            f"status={'IN_FOCUS' if symbol in focus_set else 'NOT_IN_FOCUS'}"
        )
        _pipeline_stage_log(
            stage="FOCUS",
            symbol=symbol,
            strategy=strategy_name,
            mode=mode.value,
            session=session.value,
            outcome="INCLUDED" if symbol in focus_set else "EXCLUDED",
            reason_code="FOCUS_PASS" if symbol in focus_set else "FOCUS_EXCLUDED",
        )
        if symbol not in focus_set:
            first_blocker_by_symbol.setdefault(symbol, "FOCUS_EXCLUDED")
            first_blocker_reason_by_symbol.setdefault(symbol, "FOCUS_EXCLUDED")
            print(
                "[PIPELINE] "
                f"symbol={symbol} setup_family=NONE trigger_type=NONE "
                "pipeline_outcome=NO_SETUP reason=NOT_IN_FOCUS"
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
    pipeline_outcomes: dict[str, str] = {symbol: TERMINAL_STATES["NO_SETUP"] for symbol in watchlist}
    decision_waterfall: dict[str, dict[str, str]] = {
        symbol: {
            "setup": "NO",
            "trigger": "NO",
            "intent": "NONE",
            "intent_reason": "N/A",
            "risk": "N/A",
            "risk_reason": "N/A",
            "execution": "N/A",
            "execution_reason": "N/A",
        }
        for symbol in watchlist
    }
    symbol_setup_family: dict[str, str] = {symbol: "NONE" for symbol in watchlist}
    symbol_trigger_type: dict[str, str] = {symbol: "NONE" for symbol in watchlist}
    passed_setup = 0
    passed_trigger = 0
    generated_intents = 0
    risk_allowed = 0
    selected_by_arbitrator = 0
    executed = 0
    forced_intent_ids: set[str] = set()
    price_authority_reasons: Counter[str] = Counter()
    symbols_with_ibkr_price: set[str] = set()
    symbols_blocked_price_authority: set[str] = set()
    symbols_blocked_no_price: set[str] = set()
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
            print(
                "[ROSS][INPUT] "
                f"symbol={symbol} strategy={strategy_name} mode={mode.value} session={session.value} "
                "inputs=pattern_evaluator"
            )
            data_quality = scanner_payload.get("data_quality_by_symbol", {}).get(symbol, [])
            inputs = _build_synthetic_inputs(symbol, data_quality, session.value)
            summary = evaluator.evaluate([inputs])
            best_setup = summary.best_long_setup or summary.best_short_setup
            best_name = best_setup.pattern_name if best_setup else "NONE"
            best_conf = best_setup.confidence if best_setup else 0.0
            setup_detected = best_name not in {"NONE", ""}
            trigger_ready_now = setup_detected and best_conf >= 0.20
            setup_family = best_name if setup_detected else "NONE"
            trigger_type = "BREAKOUT_HIGH" if setup_detected else "NONE"
            symbol_setup_family[symbol] = setup_family
            symbol_trigger_type[symbol] = trigger_type
            if not setup_detected:
                pipeline_outcomes[symbol] = TERMINAL_STATES["NO_SETUP"]
                first_blocker_by_symbol.setdefault(symbol, "NO_SETUP_DETECTED")
                first_blocker_reason_by_symbol.setdefault(symbol, "NO_PATTERN_DETECTED")
            elif not trigger_ready_now:
                pipeline_outcomes[symbol] = TERMINAL_STATES["SETUP_NO_TRIGGER"]
                decision_waterfall[symbol]["setup"] = "YES"
                decision_waterfall[symbol]["intent_reason"] = "BLOCKED_BY_STRUCTURE"
                first_blocker_by_symbol.setdefault(symbol, "SETUP_DETECTED_TRIGGER_NOT_FIRED")
                first_blocker_reason_by_symbol.setdefault(symbol, "TRIGGER_NOT_READY")
            else:
                pipeline_outcomes[symbol] = TERMINAL_STATES["TRIGGER_READY"]
                decision_waterfall[symbol]["setup"] = "YES"
                decision_waterfall[symbol]["trigger"] = "YES"
            print(
                "[ROSS][SETUP_RESULT] "
                f"symbol={symbol} strategy={strategy_name} mode={mode.value} session={session.value} "
                f"outcome={'DETECTED' if setup_detected else 'NONE'} setup={setup_family}"
            )
            print(
                "[ROSS][TRIGGER_RESULT] "
                f"symbol={symbol} strategy={strategy_name} mode={mode.value} session={session.value} "
                f"outcome={'FIRED' if trigger_ready_now else 'NOT_FIRED'} reason={'TRIGGER_READY' if trigger_ready_now else 'TRIGGER_NOT_READY'}"
            )
            _pipeline_stage_log(
                stage="SETUP_EVAL",
                symbol=symbol,
                strategy=strategy_name,
                mode=mode.value,
                session=session.value,
                outcome="DETECTED" if setup_detected else "NONE",
                reason_code=best_name if setup_detected else "NO_PATTERN_DETECTED",
            )
            print(
                f"[TRIGGER] symbol={symbol} setup_family={setup_family} "
                f"trigger_type={trigger_type} trigger_ready_now={str(trigger_ready_now).lower()}"
            )
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
                f"reason={'PRICE_ACTION_TRIGGER' if trigger_ready_now else 'TRIGGER_NOT_READY'}"
            )
            _pipeline_stage_log(
                stage="TRIGGER",
                symbol=symbol,
                strategy=strategy_name,
                mode=mode.value,
                session=session.value,
                outcome="FIRED" if trigger_ready_now else "NOT_FIRED",
                reason_code="PRICE_ACTION_TRIGGER" if trigger_ready_now else "TRIGGER_NOT_READY",
            )

            strategy_id = "RossMomentumStrategy"
            try:
                trade_intents = build_trade_intents(
                    strategy_id,
                    symbol,
                    summary,
                    system_health_degraded=bool(data_quality_flags.get(symbol)),
                    trigger_ready_now=trigger_ready_now,
                    session=session.value,
                )
            except TypeError:
                # Backward compatibility for test mocks
                try:
                    trade_intents = build_trade_intents(
                        strategy_id,
                        symbol,
                        summary,
                        trigger_ready_now=trigger_ready_now,
                    )
                except TypeError:
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
                print(
                    f"[PRICE][RESOLUTION] symbol={symbol} mode={mode.value} "
                    f"resolved_price={entry_price} source={entry_price_source}"
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
                    symbols_blocked_no_price.add(symbol)
                    missing_reason = "IBKR_SNAPSHOT_UNAVAILABLE" if str(exc.reason) == "NO_VALID_PRICE_SOURCE" else "NO_ENTRY_PRICE_RESOLVED"
                    print(f"[PRICE][BLOCK] symbol={symbol} mode={mode.value} reason={missing_reason}")
                    print(f"[PIPELINE][BLOCK] symbol={symbol} reason=PRICE_AUTHORITY")
                    print(f"[PIPELINE][INTENT] symbol={symbol} created=false reason=BLOCKED_BY_INVALID_INPUT")
                    print(
                        "[ROSS][INTENT_RESULT] "
                        f"symbol={symbol} strategy={strategy_name} mode={mode.value} session={session.value} "
                        "outcome=NOT_CREATED reason=BLOCKED_BY_INVALID_INPUT"
                    )
                    print(
                        "[ROSS][BLOCKER] "
                        f"symbol={symbol} blocker=TRIGGER_FIRED_NO_INTENT reason=BLOCKED_BY_INVALID_INPUT"
                    )
                    first_blocker_by_symbol.setdefault(symbol, "TRIGGER_FIRED_NO_INTENT")
                    first_blocker_reason_by_symbol.setdefault(symbol, "BLOCKED_BY_INVALID_INPUT")
                    decision_waterfall[symbol]["intent"] = "BLOCKED"
                    decision_waterfall[symbol]["intent_reason"] = "BLOCKED_BY_INVALID_INPUT"
                    if trigger_ready_now:
                        pipeline_outcomes[symbol] = TERMINAL_STATES["TRIGGER_BLOCKED_BY_POLICY"]
                        print(
                            f"[DECISION][ERROR] TRIGGER_WITHOUT_INTENT symbol={symbol} "
                            f"setup_family={setup_family} trigger_type={trigger_type} reason=BLOCKED_BY_INVALID_INPUT"
                        )
                    continue
            authority_verdict = _enforce_canonical_price_authority(
                symbol=symbol,
                mode=mode,
                session=session.value,
                entry_price=entry_price,
                entry_price_source=entry_price_source,
                scanner_payload=scanner_payload,
            )
            entry_price_source = authority_verdict.normalized_source
            if mode == RunMode.PAPER:
                assert entry_price_source in _CANONICAL_PRICE_SOURCES, f"NO_IBKR_PRICE_AUTHORITY:{entry_price_source}"
            if mode in {RunMode.PAPER, RunMode.LIVE} and authority_verdict.allowed:
                symbols_with_ibkr_price.add(symbol)
            if not authority_verdict.allowed:
                symbols_blocked_price_authority.add(symbol)
                price_authority_reasons[authority_verdict.reason_code] += 1
                print(f"[PRICE][BLOCK] symbol={symbol} mode={mode.value} reason={authority_verdict.reason_code}")
                print(f"[PIPELINE][BLOCK] symbol={symbol} reason=PRICE_AUTHORITY detail={authority_verdict.reason}")
                print(f"[PIPELINE][INTENT] symbol={symbol} created=false reason=BLOCKED_BY_PRICE_AUTHORITY")
                print(
                    "[ROSS][INTENT_RESULT] "
                    f"symbol={symbol} strategy={strategy_name} mode={mode.value} session={session.value} "
                    "outcome=NOT_CREATED reason=BLOCKED_BY_POLICY"
                )
                print(
                    "[ROSS][BLOCKER] "
                    f"symbol={symbol} blocker=TRIGGER_FIRED_NO_INTENT reason=BLOCKED_BY_POLICY"
                )
                first_blocker_by_symbol.setdefault(symbol, "TRIGGER_FIRED_NO_INTENT")
                first_blocker_reason_by_symbol.setdefault(symbol, "BLOCKED_BY_POLICY")
                decision_waterfall[symbol]["intent"] = "BLOCKED"
                decision_waterfall[symbol]["intent_reason"] = "BLOCKED_BY_POLICY"
                if trigger_ready_now:
                    pipeline_outcomes[symbol] = TERMINAL_STATES["TRIGGER_BLOCKED_BY_POLICY"]
                    print(
                        f"[DECISION][ERROR] TRIGGER_WITHOUT_INTENT symbol={symbol} "
                            f"setup_family={setup_family} trigger_type={trigger_type} reason=BLOCKED_BY_POLICY"
                        )
                continue
            if mode == RunMode.SIM:
                print(
                    f"[PIPELINE][PRICE_AUTHORITY_BYPASS] symbol={symbol} mode={mode.value} "
                    f"reason={authority_verdict.reason} source={entry_price_source}"
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
                            **({"price_authority": "SIM_MODE_BYPASS"} if mode == RunMode.SIM else {}),
                        },
                    )
                ]
                forced_intent_ids.add(trade_intents[0].intent_id)
                print(f"[DEBUG][FORCED_PATH] intent_created symbol={symbol} intent_id={trade_intents[0].intent_id}")
                print(f"[PIPELINE][INTENT] symbol={symbol} created=true forced=true intent_id={trade_intents[0].intent_id}")
            print(
                "[ROSS][TRIGGER_AUTHORITY] "
                f"symbol={symbol} setup_family={setup_family} trigger_ready_now={str(trigger_ready_now).lower()} "
                f"strategy_trigger_fired={str(trigger_ready_now).lower()} "
                f"decision={'EMIT_INTENT' if bool(trade_intents) else 'BLOCK'} "
                f"block_reason={'NONE' if bool(trade_intents) else 'BLOCKED_BY_POLICY'}"
            )
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
                                    {"price_authority": "NON_CANONICAL_ALLOWED_SIM"}
                                    if fallback_used
                                    else {}
                                ),
                            },
                        )
                    )
                if fallback_used and isinstance(intents[-1], TradeIntentRecord):
                    intents[-1].metadata.setdefault("price_source", entry_price_source)
                    intents[-1].metadata["price_authority"] = "NON_CANONICAL_ALLOWED_SIM"
                    if "NON_LIVE_PRICE" not in intents[-1].tags:
                        intents[-1].tags.append("NON_LIVE_PRICE")
                generated_intents += 1
                decision_waterfall[symbol]["intent"] = "EMITTED"
                decision_waterfall[symbol]["intent_reason"] = "INTENT_EMITTED"
                print(f"[PIPELINE][INTENT] symbol={symbol} created=true forced=false intent_id={intent.intent_id}")
                _pipeline_stage_log(
                    stage="INTENT",
                    symbol=symbol,
                    strategy=strategy_name,
                    mode=mode.value,
                    session=session.value,
                    outcome="CREATED",
                    reason_code="INTENT_CREATED",
                )
                print(
                    f"[INTENT] symbol={symbol} setup_family={setup_family} "
                    f"trigger_type={trigger_type} intent_id={intent.intent_id}"
                )
            if trigger_ready_now and trade_intents:
                pipeline_outcomes[symbol] = TERMINAL_STATES["INTENT_EMITTED"]
                print(
                    "[ROSS][INTENT_RESULT] "
                    f"symbol={symbol} strategy={strategy_name} mode={mode.value} session={session.value} "
                    "outcome=CREATED reason=INTENT_CREATED"
                )
                print(
                    f"[DECISION][INTENT_CREATED] symbol={symbol} setup_family={setup_family} "
                    f"trigger_type={trigger_type}"
                )
            if not trade_intents:
                no_intent_reason = "BLOCKED_BY_POLICY" if trigger_ready_now else "BLOCKED_BY_STRUCTURE"
                print(f"[PIPELINE][INTENT] symbol={symbol} created=false reason={no_intent_reason}")
                _pipeline_stage_log(
                    stage="INTENT",
                    symbol=symbol,
                    strategy=strategy_name,
                    mode=mode.value,
                    session=session.value,
                    outcome="NOT_CREATED",
                    reason_code=no_intent_reason,
                )
                print(
                    "[ROSS][INTENT_RESULT] "
                    f"symbol={symbol} strategy={strategy_name} mode={mode.value} session={session.value} "
                    f"outcome=NOT_CREATED reason={no_intent_reason}"
                )
                print(
                    "[ROSS][BLOCKER] "
                    f"symbol={symbol} blocker={'TRIGGER_FIRED_NO_INTENT' if trigger_ready_now else 'SETUP_DETECTED_TRIGGER_NOT_FIRED'} "
                    f"reason={no_intent_reason}"
                )
                first_blocker_by_symbol.setdefault(
                    symbol,
                    "TRIGGER_FIRED_NO_INTENT" if trigger_ready_now else "SETUP_DETECTED_TRIGGER_NOT_FIRED",
                )
                first_blocker_reason_by_symbol.setdefault(symbol, no_intent_reason)
                decision_waterfall[symbol]["intent"] = "BLOCKED"
                decision_waterfall[symbol]["intent_reason"] = no_intent_reason
                if trigger_ready_now:
                    pipeline_outcomes[symbol] = TERMINAL_STATES["TRIGGER_BLOCKED_BY_POLICY"]
                    print(
                        f"[DECISION][ERROR] TRIGGER_WITHOUT_INTENT symbol={symbol} "
                        f"setup_family={setup_family} trigger_type={trigger_type} reason={no_intent_reason}"
                    )
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
        _pipeline_stage_log(
            stage="RISK",
            symbol=output.symbol,
            strategy=strategy_name,
            mode=mode.value,
            session=session.value,
            outcome="ALLOW" if risk_pass else "BLOCK",
            reason_code=output.block_reason or "PASS",
        )
        if not risk_pass:
            first_blocker_by_symbol.setdefault(output.symbol, "INTENT_BLOCKED_BY_RISK")
            first_blocker_reason_by_symbol.setdefault(output.symbol, output.block_reason or "RISK_BLOCKED")
        decision_waterfall[output.symbol]["risk"] = "ALLOW" if risk_pass else "BLOCK"
        decision_waterfall[output.symbol]["risk_reason"] = output.block_reason or "PASS"
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
    position_book: dict[str, dict[str, float]] = {}
    print(
        "[MODE][EXECUTION_CONTEXT] "
        f"effective_mode={mode.value} trade_enabled={mode_authority.trade_enabled} "
        f"scan_only={mode_authority.scan_only} execution_enabled={mode_authority.execution_enabled} "
        f"intents_present={bool(arbitrated_decisions)} intent_count={len(arbitrated_decisions)}"
    )
    execution_candidates: List[RiskDecisionRecord] = []
    blocked_candidates: List[ExecutionEvent] = []
    execution_skipped = execution_intent.scan_only or (not mode_authority.trade_enabled)
    if not arbitrated_decisions:
        print("[PIPELINE][EXECUTION_GATE] symbol=NONE eligible=false reason=NO_INTENTS")
    for decision in arbitrated_decisions:
        print(
            "[EXECUTION][INTENT_RECEIVED] "
            f"symbol={decision.symbol} strategy={strategy_name} mode={mode.value} session={session.value} "
            f"intent_id={decision.intent_id} approved_quantity={int(decision.approved_quantity)}"
        )
        print(
            f"[EXECUTION] symbol={decision.symbol} "
            f"setup_family={symbol_setup_family.get(decision.symbol, 'NONE')} "
            f"trigger_type={symbol_trigger_type.get(decision.symbol, 'NONE')}"
        )
        if execution_skipped:
            print(f"[EXECUTION][PRECHECK] symbol={decision.symbol} passed=false reason=SCAN_ONLY_OR_DISABLED")
            print(f"[EXECUTION][SKIPPED] symbol={decision.symbol} reason=SCAN_ONLY_OR_DISABLED")
            blocked_candidates.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail="reason=SCAN_ONLY_OR_DISABLED",
                )
            )
            pipeline_outcomes[decision.symbol] = TERMINAL_STATES["BLOCKED_BY_EXECUTION_PRECHECK"]
            _pipeline_stage_log(
                stage="EXECUTION",
                symbol=decision.symbol,
                strategy=strategy_name,
                mode=mode.value,
                session=session.value,
                outcome="SKIPPED",
                reason_code="SCAN_ONLY_OR_DISABLED",
            )
            first_blocker_by_symbol.setdefault(decision.symbol, "INTENT_NOT_ROUTED_TO_EXECUTION")
            first_blocker_reason_by_symbol.setdefault(decision.symbol, "SCAN_ONLY_OR_DISABLED")
            decision_waterfall[decision.symbol]["execution"] = "SKIPPED"
            decision_waterfall[decision.symbol]["execution_reason"] = "SCAN_ONLY_OR_DISABLED"
            continue
        if mode in {RunMode.PAPER, RunMode.LIVE} and health_status == HealthStatus.DEGRADED:
            reason = "DATA_QUALITY_DEGRADED"
            print("[EXECUTION_BLOCK][DATA_QUALITY] status=DEGRADED")
            print(f"[EXECUTION][PRECHECK] symbol={decision.symbol} passed=false reason={reason}")
            print(f"[EXECUTION][BLOCK] symbol={decision.symbol} reason={reason}")
            blocked_candidates.append(
                ExecutionEvent(
                    symbol=decision.symbol,
                    intent_id=decision.intent_id,
                    action="BLOCKED",
                    detail=f"reason={reason}",
                )
            )
            pipeline_outcomes[decision.symbol] = TERMINAL_STATES["BLOCKED_BY_EXECUTION_PRECHECK"]
            _pipeline_stage_log(
                stage="EXECUTION",
                symbol=decision.symbol,
                strategy=strategy_name,
                mode=mode.value,
                session=session.value,
                outcome="BLOCK",
                reason_code=reason,
            )
            first_blocker_by_symbol.setdefault(decision.symbol, "EXECUTION_PRECHECK_FAIL")
            first_blocker_reason_by_symbol.setdefault(decision.symbol, reason)
            decision_waterfall[decision.symbol]["execution"] = "REJECTED"
            decision_waterfall[decision.symbol]["execution_reason"] = reason
            continue
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
        print(
            f"[EXECUTION][PRECHECK] symbol={decision.symbol} passed={str(eligible).lower()} "
            f"reason={'PRECHECK_PASS' if eligible else 'EXECUTION_GATES_NOT_SATISFIED'}"
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
            pipeline_outcomes[decision.symbol] = TERMINAL_STATES["BLOCKED_BY_EXECUTION_PRECHECK"]
            _pipeline_stage_log(
                stage="EXECUTION",
                symbol=decision.symbol,
                strategy=strategy_name,
                mode=mode.value,
                session=session.value,
                outcome="BLOCK",
                reason_code=reason,
            )
            first_blocker_by_symbol.setdefault(decision.symbol, "EXECUTION_PRECHECK_FAIL")
            first_blocker_reason_by_symbol.setdefault(decision.symbol, reason)
            decision_waterfall[decision.symbol]["execution"] = "REJECTED"
            decision_waterfall[decision.symbol]["execution_reason"] = reason
            continue
        print(f"[EXECUTION][QUALIFY] symbol={decision.symbol} passed=true reason=EXECUTION_ELIGIBLE")
        print(f"[EXECUTION][ORDER_BUILD] symbol={decision.symbol} passed=true order_type=MKT tif=DAY")
        print(
            "[EXECUTION][SUBMIT_ATTEMPT] "
            f"symbol={decision.symbol} qty={int(decision.approved_quantity)} order_type=MKT mode=PAPER"
        )
        _pipeline_stage_log(
            stage="EXECUTION",
            symbol=decision.symbol,
            strategy=strategy_name,
            mode=mode.value,
            session=session.value,
            outcome="ATTEMPT",
            reason_code="SUBMIT_ATTEMPT",
        )
        execution_candidates.append(decision)

    if intents:
        execution_events = execute_intents(mode=mode, decisions=execution_candidates)
    else:
        execution_events = []
    execution_events.extend(blocked_candidates)
    execution_state_counts = {"submitted": 0, "acknowledged": 0, "working": 0, "partial_fills": 0, "filled": 0}
    execution_attempts = 0
    duplicate_working_order_blocks = 0
    for event in execution_events:
        broker_order_id = getattr(event, "broker_order_id", None)
        filled_quantity = int(getattr(event, "filled_quantity", 0) or 0)
        remaining_quantity = int(getattr(event, "remaining_quantity", 0) or 0)
        broker_status = str(getattr(event, "broker_status", "UNKNOWN") or "UNKNOWN")
        normalized_action = str(event.action or "").upper()
        normalized_broker_status = broker_status.upper()
        is_submitted = normalized_action == "SUBMITTED"
        is_acknowledged = normalized_action == "ACKNOWLEDGED" or (
            is_submitted and broker_order_id is not None
        )
        is_working = (
            normalized_action == "WORKING"
            or (is_submitted and remaining_quantity > 0)
            or normalized_broker_status in {"SUBMITTED", "PRESUBMITTED", "ACKNOWLEDGED"}
        )
        is_filled = (
            normalized_action == "FILLED"
            or str(getattr(event, "event_type", "") or "").upper() == "ORDER_FILLED"
            or filled_quantity > 0
            or normalized_broker_status == "FILLED"
        )
        if is_submitted:
            execution_state_counts["submitted"] += 1
        if is_acknowledged:
            execution_state_counts["acknowledged"] += 1
        if is_working:
            execution_state_counts["working"] += 1
        if is_filled:
            execution_state_counts["filled"] += 1
        if str(getattr(event, "event_type", "") or "").upper() == "ORDER_PARTIALLY_FILLED":
            execution_state_counts["partial_fills"] += 1
        if is_submitted or is_acknowledged or is_working or is_filled:
            execution_attempts += 1
        if "DUPLICATE_WORKING_ORDER" in str(event.detail or ""):
            duplicate_working_order_blocks += 1
        print(
            "[EXECUTION][SUBMIT_RESULT] "
            f"symbol={event.symbol} submitted={event.action == 'SUBMITTED'} "
            f"order_id={broker_order_id if broker_order_id is not None else 'MISSING'} reason={event.detail}"
        )
        _pipeline_stage_log(
            stage="SUBMISSION_RESULT",
            symbol=event.symbol,
            strategy=strategy_name,
            mode=mode.value,
            session=session.value,
            outcome=event.action,
            reason_code=str(event.detail or "NONE"),
        )
        if broker_order_id is not None:
            print(f"[EXECUTION][ORDER_ID_CAPTURED] symbol={event.symbol} order_id={broker_order_id}")
        print(f"[EXECUTION] {event.symbol} {event.action} ({event.detail})")
        execution_pass = event.action in {"SUBMITTED", "WOULD_PLACE"}
        if event.action == "SUBMITTED" and broker_order_id is None:
            print(
                f"[INVARIANT][FAIL] submitted_order_without_broker_id symbol={event.symbol} intent_id={event.intent_id}"
            )
            execution_pass = False
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
            fill_event = str(getattr(event, "event_type", "") or "")
            event_source = str(getattr(event, "source", "IBKR_EVENT") or "IBKR_EVENT")
            if fill_event == "ORDER_FILLED" or filled_quantity > 0:
                if fill_event == "ORDER_PARTIALLY_FILLED":
                    print(
                        f"[LIFECYCLE] ORDER_PARTIALLY_FILLED symbol={event.symbol} order_id={broker_order_id} "
                        f"filled_qty={filled_quantity} remaining_qty={remaining_quantity}"
                    )
                print(
                    f"[EXECUTION][FILL] symbol={event.symbol} order_id={broker_order_id} "
                    f"filled_qty={filled_quantity} remaining_qty={remaining_quantity}"
                )
                print(
                    f"[LIFECYCLE] ORDER_FILLED symbol={event.symbol} order_id={broker_order_id} "
                    f"filled_qty={filled_quantity} source={event_source}"
                )
                symbol_key = str(event.symbol or "").upper()
                if symbol_key:
                    existing_position = position_book.get(symbol_key)
                    fill_price = event.avg_fill_price
                    fill_qty = max(0, filled_quantity)
                    if existing_position is None:
                        position_book[symbol_key] = {"qty": float(fill_qty), "avg_price": float(fill_price or 0.0)}
                    else:
                        prev_qty = float(existing_position["qty"])
                        prev_avg = float(existing_position["avg_price"])
                        total_qty = prev_qty + float(fill_qty)
                        if total_qty > 0 and fill_price is not None:
                            weighted_avg = ((prev_qty * prev_avg) + (float(fill_qty) * float(fill_price))) / total_qty
                        else:
                            weighted_avg = prev_avg
                        existing_position["qty"] = total_qty
                        existing_position["avg_price"] = weighted_avg
                    print(
                        f"[LIFECYCLE] POSITION_OPENED symbol={symbol_key} "
                        f"qty={int(position_book[symbol_key]['qty'])} "
                        f"price={position_book[symbol_key]['avg_price']:.4f}"
                    )
                    pending_entries = max(0, pending_entries - 1)
        elif execution_pass:
            working_orders += 1 if event.action == "WOULD_PLACE" else 0
        execution_outcome = "WORKING_NO_FILL_YET"
        if filled_quantity > 0 and remaining_quantity > 0:
            execution_outcome = "PARTIALLY_FILLED"
        elif filled_quantity > 0 and remaining_quantity == 0:
            execution_outcome = "FILLED_POSITION_OPEN"
        elif is_acknowledged:
            execution_outcome = "ORDER_ACKNOWLEDGED"
        elif is_submitted:
            execution_outcome = "ORDER_SUBMITTED"
        print(
            f"[PIPELINE][EXECUTION] symbol={event.symbol} "
            f"executed={str(execution_pass).lower()} action={event.action} outcome={execution_outcome}"
        )
        if event.action in {"SUBMITTED", "WOULD_PLACE"}:
            pipeline_outcomes[event.symbol] = TERMINAL_STATES["ORDER_SUBMITTED"]
            if broker_order_id is None and event.action == "SUBMITTED":
                first_blocker_by_symbol.setdefault(event.symbol, "ORDER_ACK_MISSING")
                first_blocker_reason_by_symbol.setdefault(event.symbol, "MISSING_BROKER_ORDER_ID")
            elif int(getattr(event, "filled_quantity", 0) or 0) <= 0:
                first_blocker_by_symbol.setdefault(event.symbol, "FILL_PENDING")
                first_blocker_reason_by_symbol.setdefault(event.symbol, "FILL_PENDING")
            decision_waterfall[event.symbol]["execution"] = execution_outcome if event.action == "SUBMITTED" else "ORDER_SUBMITTED"
            decision_waterfall[event.symbol]["execution_reason"] = event.detail
        elif event.action == "BLOCKED":
            pipeline_outcomes[event.symbol] = TERMINAL_STATES["ORDER_REJECTED"]
            first_blocker_by_symbol.setdefault(event.symbol, "IBKR_SUBMISSION_FAIL")
            first_blocker_reason_by_symbol.setdefault(event.symbol, str(event.detail or "ORDER_REJECTED"))
            decision_waterfall[event.symbol]["execution"] = "REJECTED"
            decision_waterfall[event.symbol]["execution_reason"] = event.detail
        if event.intent_id in forced_intent_ids and execution_pass:
            print(f"[DEBUG][FORCED_PATH] sent_to_execution symbol={event.symbol} intent_id={event.intent_id}")
    execution_event_symbols = {str(event.symbol or "").upper() for event in execution_events if getattr(event, "symbol", None)}
    for decision in arbitrated_decisions:
        symbol_key = str(decision.symbol or "").upper()
        if symbol_key and symbol_key not in execution_event_symbols:
            first_blocker_by_symbol.setdefault(symbol_key, "INTENT_NOT_ROUTED_TO_EXECUTION")
            first_blocker_reason_by_symbol.setdefault(symbol_key, "NO_EXECUTION_EVENT")
            _pipeline_stage_log(
                stage="EXECUTION",
                symbol=symbol_key,
                strategy=strategy_name,
                mode=mode.value,
                session=session.value,
                outcome="NOT_ROUTED",
                reason_code="NO_EXECUTION_EVENT",
            )
            print(
                "[PIPELINE][EXECUTION] "
                f"symbol={symbol_key} strategy={strategy_name} mode={mode.value} session={session.value} "
                "outcome=NOT_ROUTED reason_code=NO_EXECUTION_EVENT"
            )
    for decision in risk_decisions:
        if decision.decision not in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"}:
            pipeline_outcomes[decision.symbol] = TERMINAL_STATES["BLOCKED_BY_RISK"]
    for symbol in watchlist:
        outcome = pipeline_outcomes.get(symbol)
        if outcome is None:
            raise RuntimeError(f"[PIPELINE][ERROR] SYMBOL_WITHOUT_TERMINAL_OUTCOME symbol={symbol}")
        print(
            f"[PIPELINE] symbol={symbol} setup_family={symbol_setup_family.get(symbol, 'NONE')} "
            f"trigger_type={symbol_trigger_type.get(symbol, 'NONE')} pipeline_outcome={outcome}"
        )
        first_blocker_by_symbol.setdefault(symbol, "OTHER_UNCLASSIFIED")
        first_blocker_reason_by_symbol.setdefault(symbol, "OTHER_UNCLASSIFIED")
    print("[PIPELINE][SUMMARY]")
    print(f"total_symbols={len(watchlist)}")
    print(f"intents_created={len(intents)}")
    print(f"execution_attempted={len(execution_candidates)}")
    blocked_count = sum(1 for value in pipeline_outcomes.values() if value in {"BLOCKED_BY_RISK", "BLOCKED_BY_EXECUTION_PRECHECK"})
    print(f"blocked_count={blocked_count}")
    print(f"no_setup_count={sum(1 for value in pipeline_outcomes.values() if value == 'NO_SETUP')}")
    lifecycle_snapshot = runtime_lifecycle_snapshot()
    open_positions = int(lifecycle_snapshot["open_position_count"])
    executed = execution_attempts
    print(
        f"[LIFECYCLE][PORTFOLIO] open_positions={open_positions} "
        f"working_orders={lifecycle_snapshot['working_order_count']} pending_entries={lifecycle_snapshot['pending_entry_count']}"
    )
    print("[EXECUTION][SUMMARY]")
    print(f"submitted={execution_state_counts['submitted']}")
    print(f"acknowledged={execution_state_counts['acknowledged']}")
    print(f"working={lifecycle_snapshot['working_order_count']}")
    print(f"partial_fills={lifecycle_snapshot['partially_filled_order_count']}")
    print(f"filled={lifecycle_snapshot['fully_filled_order_count']}")
    print(f"open_positions={lifecycle_snapshot['open_position_count']}")
    print(f"pending_entries={lifecycle_snapshot['pending_entry_count']}")
    print(f"partial_positions={lifecycle_snapshot['partial_position_open_count']}")
    print(f"reducing_positions={lifecycle_snapshot['reducing_position_count']}")
    print(f"closed_positions={lifecycle_snapshot['closed_position_count']}")
    print(f"unmatched_callbacks={lifecycle_snapshot['unmatched_callbacks_count']}")
    print(f"reconciled_orders={lifecycle_snapshot['reconciled_orders_count']}")
    print(f"reconciled_positions={lifecycle_snapshot['reconciled_positions_count']}")
    print(f"duplicate_working_order_blocks={duplicate_working_order_blocks}")
    print(f"fill_authority_state={fill_authority_state()}")
    for symbol in watchlist:
        wf = decision_waterfall[symbol]
        print(
            "[ROSS][DECISION_WATERFALL] "
            f"symbol={symbol} setup={wf['setup']} trigger={wf['trigger']} "
            f"intent={wf['intent']} intent_reason={wf['intent_reason']} "
            f"risk={wf['risk']} risk_reason={wf['risk_reason']} "
            f"execution={wf['execution']} execution_reason={wf['execution_reason']}"
        )
    terminal_counts = Counter(pipeline_outcomes.values())
    block_reason_counts = Counter(
        wf["intent_reason"] for wf in decision_waterfall.values() if wf["intent_reason"] not in {"N/A", "INTENT_EMITTED"}
    )
    print(
        "[ROSS][CYCLE_ROOT_CAUSE] "
        f"evaluated_symbols={len(watchlist)} setup_count={sum(1 for wf in decision_waterfall.values() if wf['setup'] == 'YES')} "
        f"trigger_count={sum(1 for wf in decision_waterfall.values() if wf['trigger'] == 'YES')} "
        f"intent_count={sum(1 for wf in decision_waterfall.values() if wf['intent'] == 'EMITTED')} "
        f"risk_allowed_count={sum(1 for wf in decision_waterfall.values() if wf['risk'] == 'ALLOW')} "
        f"execution_submit_count={sum(1 for wf in decision_waterfall.values() if wf['execution'] in {'ORDER_SUBMITTED', 'ORDER_ACKNOWLEDGED', 'WORKING_NO_FILL_YET', 'PARTIALLY_FILLED', 'FILLED_POSITION_OPEN'})} "
        f"dominant_terminal_state={(terminal_counts.most_common(1)[0][0] if terminal_counts else 'NONE')} "
        f"dominant_block_reason={(block_reason_counts.most_common(1)[0][0] if block_reason_counts else 'NONE')}"
    )
    blocker_counts = Counter(
        blocker for blocker in first_blocker_by_symbol.values() if blocker in PIPELINE_BLOCKER_TAXONOMY
    )
    dominant_blocker = blocker_counts.most_common(1)[0][0] if blocker_counts else "OTHER_UNCLASSIFIED"
    print(
        "[PIPELINE][CYCLE_SUMMARY] "
        f"scanned_count={len(scanned_symbols)} watchlist_count={len(watchlist)} focus_count={len(focus)} "
        f"setup_detected_count={passed_setup} trigger_fired_count={passed_trigger} intent_count={generated_intents} "
        f"risk_allowed_count={risk_allowed} execution_attempt_count={len(execution_candidates)} "
        f"submission_success_count={execution_state_counts['submitted']} dominant_blocker={dominant_blocker}"
    )
    for symbol, blocker in sorted(first_blocker_by_symbol.items()):
        print(
            "[PIPELINE][BLOCKER] "
            f"symbol={symbol} blocker={blocker} reason={first_blocker_reason_by_symbol.get(symbol, 'NONE')}"
        )
    print(
        "[LIFECYCLE][RISK_SIGNALS] "
        f"trade_flow_active={str(execution_attempts > 0).lower()} "
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
    if execution_attempts == 0:
        if passed_setup > 0 and passed_trigger > 0 and generated_intents > 0:
            kill_switch_active = any(
                "KILL_SWITCH" in rule
                for decision in risk_decisions
                for rule in decision.triggered_rules
            )
            portfolio_exposure = sum(float(decision.order_value) for decision in risk_decisions if decision.risk_allowed)
            last_block_reason = _derive_last_block_reason(risk_decisions)
            print(
                "[PIPELINE][ERROR] no_execution_attempts_despite_valid_pipeline "
                f"risk_allowed={risk_allowed} selected_by_arbitrator={selected_by_arbitrator} "
                f"kill_switch_active={str(kill_switch_active).lower()} "
                f"portfolio_exposure={portfolio_exposure:.2f} last_block_reason={last_block_reason}"
            )
    else:
        print(f"[PIPELINE][EXECUTION_OK] submissions_detected={execution_attempts}")
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
    submitted_symbols = {
        str(event.symbol).upper()
        for event in execution_events
        if str(getattr(event, "action", "")).upper() == "SUBMITTED"
    }
    dominant_price_block_reason = "NONE"
    if price_authority_reasons:
        dominant_price_block_reason = price_authority_reasons.most_common(1)[0][0]
    print(
        "[CYCLE][PRICE_AUTHORITY_SUMMARY] "
        f"cycle_id={cycle_id} evaluated={len(focus)} ibkr_ok={len(symbols_with_ibkr_price)} "
        f"blocked={len(symbols_blocked_price_authority)} no_price={len(symbols_blocked_no_price)} "
        f"intents={len({str(intent.symbol).upper() for intent in intents})} "
        f"submitted={len(submitted_symbols)} dominant_reason={dominant_price_block_reason}"
    )

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
