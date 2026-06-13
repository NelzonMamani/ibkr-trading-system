"""PR6 deterministic Ross Momentum end-to-end certification harness.

This module proves the Ross chain with fixture data and a local simulator
boundary. It intentionally does not submit broker orders or mutate runtime
scanner/watchlist/focus state.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Iterator, Sequence

from src.scanner.scanner_runner import (
    GateThresholds,
    _evaluate_focus_gates,
    _evaluate_price_gate,
    _evaluate_watchlist_gates,
)
from src.setup_engine.setup_families.breakouts import PremarketHighBreakPattern
from src.setup_engine.setup_families.momentum import MicroPullbackPattern
from src.setup_engine.setup_families.pullbacks import FlatTopBreakoutPattern
from src.setup_engine.setup_families.ross_families import ParabolicExhaustionPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.decision_policy import (
    IntentPolicyConfig,
    build_trade_intents,
)
from src.strategies.ross_momentum.patterns.pattern_base import PatternBase
from src.strategies.ross_momentum.patterns.pattern_evaluator import (
    PatternEvaluationSummary,
    PatternEvaluator,
)
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
    build_authoritative_pattern_inputs,
)
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.patterns.pattern_types import (
    Direction,
    PatternFamily,
    PatternResult,
)
from src.strategies.ross_momentum.patterns.setup_fidelity import (
    is_tradeable_entry_candidate,
)
from src.strategies.ross_momentum.policy import RossPolicy
from src.strategies.strategy_contracts import TradeIntent

_STRATEGY_ID = "RossMomentumStrategyV1"
_E2E_TAG_PREFIX = "[ROSS][E2E]"


Row = tuple[float, float, float, float, float]


@dataclass(frozen=True)
class RossE2ECandidate:
    symbol: str
    session_label: str = "RTH_OPEN"
    last_price: float = 10.37
    pct_change: float = 18.0
    rvol: float | None = 5.5
    float_millions: float | None = 8.0
    catalyst_present: bool = True
    catalyst_status: str = "PRESENT"
    volume: int = 1_200_000
    premarket_volume: int = 500_000
    bid: float = 10.36
    ask: float = 10.38
    spread: float = 0.02
    spread_pct: float = 0.01

    def scanner_context(self) -> dict[str, Any]:
        float_shares = (
            None
            if self.float_millions is None
            else int(float(self.float_millions) * 1_000_000)
        )
        return {
            "symbol": self.symbol,
            "session": self.session_label,
            "pct_change": self.pct_change,
            "scanner_rvol": self.rvol,
            "rvol": self.rvol,
            "rvol_phase": self.rvol,
            "rvol_discovery": self.rvol,
            "volume": self.volume,
            "premarket_volume": self.premarket_volume,
            "dollar_volume": float(self.last_price) * float(self.volume),
            "last_price": self.last_price,
            "float_shares": float_shares,
            "spread_pct": self.spread_pct,
            "bid": self.bid,
            "ask": self.ask,
            "catalyst_present": self.catalyst_present,
            "catalyst_status": self.catalyst_status,
            "halted": False,
            "ssr": False,
            "execution_eligible": True,
        }


@dataclass(frozen=True)
class RossE2ECase:
    name: str
    candidate: RossE2ECandidate
    expected_trade: bool
    rows: tuple[Row, ...]
    patterns: tuple[PatternBase, ...] = ()
    forced_results: tuple[PatternResult, ...] = ()
    run_mode: str = "PAPER"
    stale_10s: bool = False
    expected_no_trade_reason: str | None = None


@dataclass(frozen=True)
class RossE2EResult:
    case_name: str
    symbol: str
    expected_trade: bool
    selection_passed: bool
    watchlist_accepted: bool
    focus_accepted: bool
    watchlist_k_symbols: tuple[str, ...]
    focus_m_symbols: tuple[str, ...]
    inputs_built: bool
    setup_detected: bool
    entry_setup_detected: bool
    selected_setup: str | None
    trigger_exists: bool
    stop_exists: bool
    rationale_exists: bool
    trade_intent_created: bool
    risk_gate_called: bool
    risk_approved: bool
    execution_path: str
    execution_safe_non_live: bool
    exit_evidence: dict[str, Any]
    analytics_record: dict[str, Any]
    no_trade_reason: str | None
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _RiskGateResult:
    called: bool
    approved: bool
    reason: str


class _ForcedRegistry:
    def __init__(self, results: Sequence[PatternResult]) -> None:
        self._results = list(results)

    def run(self, inputs: PatternInputs, **kwargs: Any) -> list[PatternResult]:
        _ = inputs, kwargs
        return list(self._results)


def run_ross_e2e_suite(cases: Sequence[RossE2ECase] | None = None) -> list[RossE2EResult]:
    selected_cases = list(cases or [*build_pr6_positive_cases(), *build_pr6_negative_cases()])
    return [run_ross_e2e_case(case) for case in selected_cases]


def run_ross_e2e_case(case: RossE2ECase) -> RossE2EResult:
    candidate = case.candidate
    symbol = candidate.symbol
    print(f"{_E2E_TAG_PREFIX}[START] case={case.name} symbol={symbol} mode={case.run_mode}")

    context = candidate.scanner_context()
    thresholds = _selection_thresholds(candidate.session_label, case.run_mode)
    price_drop = _evaluate_price_gate(context, thresholds)
    watchlist_drop = price_drop or _evaluate_watchlist_gates(context, thresholds)
    watchlist_accepted = watchlist_drop is None
    watchlist_symbols = (symbol,) if watchlist_accepted else ()
    print(
        f"{_E2E_TAG_PREFIX}[SELECTION] "
        f"case={case.name} symbol={symbol} accepted={watchlist_accepted} "
        f"reason={watchlist_drop or 'PASS'}"
    )
    print(
        f"{_E2E_TAG_PREFIX}[WATCHLIST] "
        f"case={case.name} symbols={list(watchlist_symbols)}"
    )

    focus_drop = None
    if watchlist_accepted:
        focus_drop = _evaluate_focus_gates(context, thresholds)
    focus_accepted = watchlist_accepted and focus_drop is None
    focus_symbols = (symbol,) if focus_accepted else ()
    print(
        f"{_E2E_TAG_PREFIX}[FOCUS] "
        f"case={case.name} symbols={list(focus_symbols)} "
        f"reason={focus_drop or 'PASS' if focus_accepted else focus_drop or watchlist_drop}"
    )

    if not focus_accepted:
        return _terminal_result(
            case=case,
            selection_passed=watchlist_accepted,
            watchlist_accepted=watchlist_accepted,
            focus_accepted=False,
            watchlist_k_symbols=watchlist_symbols,
            focus_m_symbols=focus_symbols,
            reason=focus_drop or watchlist_drop or "selection_blocked",
            diagnostics={"selection_context": context},
        )

    inputs = _build_inputs(case)
    print(
        f"{_E2E_TAG_PREFIX}[INPUTS] "
        f"case={case.name} symbol={symbol} primary={inputs.primary_timeframe} "
        f"exec={inputs.execution_refinement_timeframe} context={inputs.context_timeframe} "
        f"flags={inputs.data_quality_flags}"
    )

    summary = _evaluate_setup(case, inputs)
    detected_results = [result for result in summary.all_results if bool(getattr(result, "detected", False))]
    best_setup = summary.best_long_setup or summary.best_short_setup
    inspected_setup = best_setup or (detected_results[0] if detected_results else None)
    entry_ok, entry_reason = is_tradeable_entry_candidate(inspected_setup) if inspected_setup is not None else (False, "no_valid_setup")
    trigger_exists = _has_trigger(inspected_setup)
    stop_exists = _has_stop(inspected_setup)
    rationale_exists = _has_rationale(inspected_setup)
    trigger_ready = bool(best_setup and entry_ok and trigger_exists and stop_exists and rationale_exists)
    print(
        f"{_E2E_TAG_PREFIX}[SETUP] "
        f"case={case.name} detected={bool(detected_results)} "
        f"entry_ready={bool(best_setup)} setup={getattr(best_setup, 'pattern_name', None)} "
        f"reason={entry_reason}"
    )

    with _temporary_env({"RUN_MODE": case.run_mode, "RUN_MODE_EFFECTIVE": case.run_mode}):
        intents = build_trade_intents(
            _STRATEGY_ID,
            symbol,
            summary,
            config=IntentPolicyConfig(min_confidence=0.6),
            trigger_ready_now=trigger_ready,
            session=candidate.session_label,
        )
    intent = intents[0] if intents else None
    print(
        f"{_E2E_TAG_PREFIX}[DECISION] "
        f"case={case.name} intents={len(intents)} reason={summary.combined_rationale_text}"
    )

    risk = _simulate_risk_gate(case, intent, summary)
    print(
        f"{_E2E_TAG_PREFIX}[RISK] "
        f"case={case.name} called={risk.called} approved={risk.approved} reason={risk.reason}"
    )

    execution_path, execution_safe = _simulate_execution(case, intent, risk)
    print(
        f"{_E2E_TAG_PREFIX}[EXECUTION_SIM] "
        f"case={case.name} path={execution_path} safe_non_live={execution_safe}"
    )

    exit_evidence = _exit_evidence(intent, execution_path)
    print(
        f"{_E2E_TAG_PREFIX}[EXIT] "
        f"case={case.name} evidence={exit_evidence.get('status')}"
    )

    no_trade_reason = None
    if not execution_safe:
        no_trade_reason = _no_trade_reason(
            watchlist_drop=watchlist_drop,
            focus_drop=focus_drop,
            summary=summary,
            entry_reason=entry_reason,
            risk=risk,
            execution_path=execution_path,
        )
    analytics_record = _analytics_record(
        case=case,
        context=context,
        inputs=inputs,
        summary=summary,
        intents=intents,
        risk=risk,
        execution_path=execution_path,
        no_trade_reason=no_trade_reason,
    )
    print(
        f"{_E2E_TAG_PREFIX}[RESULT] "
        f"case={case.name} trade={execution_safe} no_trade_reason={no_trade_reason or 'NONE'}"
    )

    return RossE2EResult(
        case_name=case.name,
        symbol=symbol,
        expected_trade=case.expected_trade,
        selection_passed=watchlist_accepted,
        watchlist_accepted=watchlist_accepted,
        focus_accepted=focus_accepted,
        watchlist_k_symbols=watchlist_symbols,
        focus_m_symbols=focus_symbols,
        inputs_built=True,
        setup_detected=bool(detected_results),
        entry_setup_detected=bool(best_setup),
        selected_setup=getattr(best_setup, "pattern_name", None),
        trigger_exists=trigger_exists,
        stop_exists=stop_exists,
        rationale_exists=rationale_exists,
        trade_intent_created=bool(intents),
        risk_gate_called=risk.called,
        risk_approved=risk.approved,
        execution_path=execution_path,
        execution_safe_non_live=execution_safe,
        exit_evidence=exit_evidence,
        analytics_record=analytics_record,
        no_trade_reason=no_trade_reason,
        diagnostics={
            "selection_context": context,
            "input_flags": list(inputs.data_quality_flags),
            "timeframe_provenance": dict(inputs.timeframe_provenance),
            "summary_veto_flags": list(summary.veto_flags),
            "entry_reason": entry_reason,
        },
    )


def build_pr6_positive_cases() -> tuple[RossE2ECase, ...]:
    return (
        RossE2ECase(
            name="positive_micro_pullback_a_quality",
            candidate=RossE2ECandidate(symbol="PR6MICRO"),
            expected_trade=True,
            rows=tuple(_micro_rows()),
            patterns=(MicroPullbackPattern(),),
            run_mode="PAPER",
        ),
        RossE2ECase(
            name="positive_flat_top_volume_expansion",
            candidate=RossE2ECandidate(symbol="PR6FLAT", session_label="RTH_MID"),
            expected_trade=True,
            rows=tuple(_flat_top_rows()),
            patterns=(FlatTopBreakoutPattern(),),
            run_mode="PAPER",
        ),
        RossE2ECase(
            name="positive_pmh_break_valid_level_volume_stop_catalyst",
            candidate=RossE2ECandidate(symbol="PR6PMH", session_label="RTH_OPEN"),
            expected_trade=True,
            rows=tuple(_pmh_break_rows()),
            patterns=(PremarketHighBreakPattern(),),
            run_mode="PAPER",
        ),
    )


def build_pr6_negative_cases() -> tuple[RossE2ECase, ...]:
    live_base = {"run_mode": "LIVE", "expected_trade": False, "rows": tuple(_micro_rows()), "patterns": (MicroPullbackPattern(),)}
    return (
        RossE2ECase(
            name="negative_no_catalyst",
            candidate=RossE2ECandidate(symbol="PR6NOCAT", catalyst_present=False, catalyst_status="DATA_UNAVAILABLE"),
            expected_no_trade_reason="DROP_NO_CATALYST",
            **live_base,
        ),
        RossE2ECase(
            name="negative_unknown_float",
            candidate=RossE2ECandidate(symbol="PR6UNKFLT", float_millions=None),
            expected_no_trade_reason="DROP_FLOAT_UNKNOWN",
            **live_base,
        ),
        RossE2ECase(
            name="negative_float_above_limit",
            candidate=RossE2ECandidate(symbol="PR6BIGFLT", float_millions=30.0),
            expected_no_trade_reason="DROP_FLOAT_MAX",
            **live_base,
        ),
        RossE2ECase(
            name="negative_low_session_rvol",
            candidate=RossE2ECandidate(symbol="PR6LOWRVOL", rvol=2.0),
            expected_no_trade_reason="DROP_RVOL_FOCUS",
            **live_base,
        ),
        RossE2ECase(
            name="negative_weak_pct_gap",
            candidate=RossE2ECandidate(symbol="PR6WEAKPCT", pct_change=3.0),
            expected_no_trade_reason="DROP_PCT_CHANGE",
            **live_base,
        ),
        RossE2ECase(
            name="negative_stale_opening_10s",
            candidate=RossE2ECandidate(symbol="PR6STALE10"),
            expected_trade=False,
            rows=tuple(_micro_rows()),
            patterns=(MicroPullbackPattern(),),
            run_mode="PAPER",
            stale_10s=True,
            expected_no_trade_reason="pr4_input_block",
        ),
        RossE2ECase(
            name="negative_missing_stop",
            candidate=RossE2ECandidate(symbol="PR6NOSTOP"),
            expected_trade=False,
            rows=tuple(_micro_rows()),
            forced_results=(_missing_stop_result(),),
            run_mode="LIVE",
            expected_no_trade_reason="missing_stop",
        ),
        RossE2ECase(
            name="negative_indicator_only_signal",
            candidate=RossE2ECandidate(symbol="PR6INDONLY"),
            expected_trade=False,
            rows=tuple(_micro_rows()),
            forced_results=(_indicator_only_result(),),
            run_mode="LIVE",
            expected_no_trade_reason="missing_trigger",
        ),
        RossE2ECase(
            name="negative_exhaustion_risk_off",
            candidate=RossE2ECandidate(symbol="PR6EXHAUST", session_label="RTH_MID"),
            expected_trade=False,
            rows=tuple(_exhaustion_rows()),
            patterns=(ParabolicExhaustionPattern(),),
            run_mode="LIVE",
            expected_no_trade_reason="risk_off_non_entry",
        ),
        RossE2ECase(
            name="negative_no_valid_setup",
            candidate=RossE2ECandidate(symbol="PR6NOSETUP", session_label="RTH_MID"),
            expected_trade=False,
            rows=tuple(_no_setup_rows()),
            patterns=(MicroPullbackPattern(),),
            run_mode="LIVE",
            expected_no_trade_reason="no_valid_setup",
        ),
    )


def _terminal_result(
    *,
    case: RossE2ECase,
    selection_passed: bool,
    watchlist_accepted: bool,
    focus_accepted: bool,
    watchlist_k_symbols: tuple[str, ...],
    focus_m_symbols: tuple[str, ...],
    reason: str,
    diagnostics: dict[str, Any],
) -> RossE2EResult:
    print(f"{_E2E_TAG_PREFIX}[INPUTS] case={case.name} status=SKIPPED reason={reason}")
    print(f"{_E2E_TAG_PREFIX}[SETUP] case={case.name} detected=False entry_ready=False reason={reason}")
    print(f"{_E2E_TAG_PREFIX}[DECISION] case={case.name} intents=0 reason={reason}")
    print(f"{_E2E_TAG_PREFIX}[RISK] case={case.name} called=False approved=False reason=NO_INTENT")
    print(f"{_E2E_TAG_PREFIX}[EXECUTION_SIM] case={case.name} path=SKIPPED safe_non_live=False")
    print(f"{_E2E_TAG_PREFIX}[EXIT] case={case.name} evidence=SKIPPED")
    print(f"{_E2E_TAG_PREFIX}[RESULT] case={case.name} trade=False no_trade_reason={reason}")
    analytics_record = {
        "case": case.name,
        "symbol": case.candidate.symbol,
        "selection_passed": selection_passed,
        "watchlist_accepted": watchlist_accepted,
        "focus_accepted": focus_accepted,
        "trade_intent_created": False,
        "execution_path": "SKIPPED",
        "no_trade_reason": reason,
        "storage_capturable": True,
    }
    return RossE2EResult(
        case_name=case.name,
        symbol=case.candidate.symbol,
        expected_trade=case.expected_trade,
        selection_passed=selection_passed,
        watchlist_accepted=watchlist_accepted,
        focus_accepted=focus_accepted,
        watchlist_k_symbols=watchlist_k_symbols,
        focus_m_symbols=focus_m_symbols,
        inputs_built=False,
        setup_detected=False,
        entry_setup_detected=False,
        selected_setup=None,
        trigger_exists=False,
        stop_exists=False,
        rationale_exists=False,
        trade_intent_created=False,
        risk_gate_called=False,
        risk_approved=False,
        execution_path="SKIPPED",
        execution_safe_non_live=False,
        exit_evidence={"status": "SKIPPED", "reason": reason},
        analytics_record=analytics_record,
        no_trade_reason=reason,
        diagnostics=diagnostics,
    )


def _selection_thresholds(session_label: str, run_mode: str) -> GateThresholds:
    policy = RossPolicy()
    stock = policy.stock_selection
    rvol = policy.rvol
    gap = policy.gap
    price = policy.price
    run_mode_key = str(run_mode or "LIVE").upper()
    execution_min_volume = int(stock.min_volume)
    premarket_min_volume = int(getattr(stock, "premarket_volume_min", stock.min_premarket_volume))
    configured_session_focus_volume = dict(getattr(stock, "session_focus_volume_min", {}) or {})
    early_rth_focus_min = max(
        premarket_min_volume,
        int(configured_session_focus_volume.get("RTH_OPEN", execution_min_volume * 0.25)),
    )
    session_focus_volume_min = {str(key).upper(): int(value) for key, value in configured_session_focus_volume.items()}
    session_focus_volume_min["RTH_OPEN"] = early_rth_focus_min
    return GateThresholds(
        min_price=float(price.minimum),
        max_price=float(price.maximum),
        min_pct_change=float(gap.discovery_threshold_for(session_label)),
        max_pct_change=gap.max_pct,
        watchlist_rvol_min=float(rvol.watchlist_threshold_for(session_label)),
        focus_rvol_min=float(rvol.focus_threshold_for(session_label)),
        focus_volume_min=execution_min_volume,
        focus_volume_min_early_rth=early_rth_focus_min,
        focus_volume_min_early_rth_ratio=0.25,
        min_volume=execution_min_volume,
        min_premarket_volume=premarket_min_volume,
        max_float=policy.float.max_shares,
        spread_max_pct=stock.spread_max_pct,
        min_dollar_volume=stock.liquidity_min_dollar_volume,
        require_price=stock.data_quality_require_price,
        require_bid_ask=stock.data_quality_require_bid_ask,
        require_catalyst=stock.require_catalyst,
        allow_halts=stock.allow_halts,
        allow_ssr=stock.allow_ssr,
        allow_unknown_float=False,
        session_focus_volume_min=session_focus_volume_min,
        min_premarket_volume_threshold=premarket_min_volume,
        focus_pct_change_min=float(gap.focus_threshold_for(session_label)),
        live_quality_pct_change_min=float(gap.live_quality_min_pct),
        live_quality_min_price=float(price.live_quality_min),
        preferred_price_min=float(price.preferred_min),
        preferred_price_max=float(price.preferred_max),
        live_quality_required=run_mode_key in {"LIVE", "READ_ONLY", "PAPER"},
        validation_override_active=False,
        run_mode=run_mode_key,
    )


def _build_inputs(case: RossE2ECase) -> PatternInputs:
    now = datetime.now(timezone.utc)
    rows = list(case.rows)
    fresh_start = now - timedelta(seconds=max(len(rows), 1) * 10)
    stale_start = now - timedelta(minutes=30)
    candidate = case.candidate
    timeframe_candles = {
        "10s": _candles(rows, start=stale_start if case.stale_10s else fresh_start),
        "1m": _candles(rows, start=fresh_start),
        "5m": _candles(rows, start=fresh_start),
    }
    return build_authoritative_pattern_inputs(
        symbol=candidate.symbol,
        session_label=candidate.session_label,
        session_phase=candidate.session_label,
        timeframe_candles=timeframe_candles,
        indicators=_default_indicators(),
        levels=_default_levels(),
        liquidity_context=LiquidityContext(
            spread=candidate.spread,
            float_millions=candidate.float_millions,
            rvol=candidate.rvol,
            volume=candidate.volume,
        ),
        news_context={
            "catalyst": "PRESENT" if candidate.catalyst_present else "MISSING",
            "catalyst_status": candidate.catalyst_status,
        },
        now=now,
    )


def _evaluate_setup(case: RossE2ECase, inputs: PatternInputs) -> PatternEvaluationSummary:
    if case.forced_results:
        evaluator = PatternEvaluator(_ForcedRegistry(case.forced_results))  # type: ignore[arg-type]
        return evaluator.evaluate([inputs])
    registry = RossPatternRegistry()
    registry._patterns = list(case.patterns)
    return PatternEvaluator(registry).evaluate([inputs])


def _simulate_risk_gate(
    case: RossE2ECase,
    intent: TradeIntent | None,
    summary: PatternEvaluationSummary,
) -> _RiskGateResult:
    if intent is None:
        return _RiskGateResult(called=False, approved=False, reason="NO_INTENT")
    if summary.veto_flags:
        return _RiskGateResult(called=True, approved=False, reason=f"VETO_FLAGS:{','.join(summary.veto_flags)}")
    if str(case.run_mode).upper() == "LIVE":
        return _RiskGateResult(called=True, approved=False, reason="LIVE_EXECUTION_NOT_CERTIFIED_BY_PR6")
    return _RiskGateResult(called=True, approved=True, reason="SIMULATED_RISK_APPROVED")


def _simulate_execution(
    case: RossE2ECase,
    intent: TradeIntent | None,
    risk: _RiskGateResult,
) -> tuple[str, bool]:
    if intent is None:
        return "SKIPPED_NO_INTENT", False
    if not risk.approved:
        return f"BLOCKED_BY_RISK:{risk.reason}", False
    if str(case.run_mode).upper() == "LIVE":
        return "BLOCKED_LIVE_NO_FAKE_TRADE", False
    return "SIMULATED_SAFE_NON_LIVE", True


def _exit_evidence(intent: TradeIntent | None, execution_path: str) -> dict[str, Any]:
    if intent is None or execution_path != "SIMULATED_SAFE_NON_LIVE":
        return {"status": "SKIPPED", "reason": execution_path}
    return {
        "status": "SIMULATED_MANAGEMENT_READY",
        "stop_model": intent.stop_model,
        "target_model": intent.target_model,
        "exit_signal_capture": "available_without_live_order",
    }


def _analytics_record(
    *,
    case: RossE2ECase,
    context: dict[str, Any],
    inputs: PatternInputs,
    summary: PatternEvaluationSummary,
    intents: Sequence[TradeIntent],
    risk: _RiskGateResult,
    execution_path: str,
    no_trade_reason: str | None,
) -> dict[str, Any]:
    return {
        "case": case.name,
        "symbol": case.candidate.symbol,
        "run_mode": case.run_mode,
        "watchlist_accepted": True,
        "focus_accepted": True,
        "input_flags": list(inputs.data_quality_flags),
        "timeframe_provenance": dict(inputs.timeframe_provenance),
        "detected_setups": [
            getattr(result, "pattern_name", "")
            for result in summary.all_results
            if bool(getattr(result, "detected", False))
        ],
        "intent_count": len(intents),
        "risk_gate_called": risk.called,
        "risk_approved": risk.approved,
        "execution_path": execution_path,
        "no_trade_reason": no_trade_reason,
        "storage_capturable": True,
        "scanner_context": {
            "pct_change": context.get("pct_change"),
            "rvol": context.get("rvol"),
            "float_shares": context.get("float_shares"),
            "catalyst_status": context.get("catalyst_status"),
        },
    }


def _no_trade_reason(
    *,
    watchlist_drop: str | None,
    focus_drop: str | None,
    summary: PatternEvaluationSummary,
    entry_reason: str,
    risk: _RiskGateResult,
    execution_path: str,
) -> str:
    if watchlist_drop:
        return watchlist_drop
    if focus_drop:
        return focus_drop
    rejection = next(
        (
            str(getattr(result, "rejection_reason"))
            for result in summary.all_results
            if getattr(result, "rejection_reason", None)
        ),
        None,
    )
    detected_any = any(bool(getattr(result, "detected", False)) for result in summary.all_results)
    if not detected_any:
        return f"no_valid_setup:{rejection}" if rejection else "no_valid_setup"
    if rejection:
        return rejection
    if entry_reason != "ok":
        return entry_reason
    if risk.called and not risk.approved:
        return risk.reason
    return execution_path


def _has_trigger(setup: Any | None) -> bool:
    return bool(setup is not None and (getattr(setup, "trigger_level", None) is not None or getattr(setup, "entry_zone", None)))


def _has_stop(setup: Any | None) -> bool:
    return bool(
        setup is not None
        and (
            getattr(setup, "stop_level", None) is not None
            or getattr(setup, "invalidation_level", None) is not None
            or getattr(setup, "stop_suggestion", None)
        )
    )


def _has_rationale(setup: Any | None) -> bool:
    rationale = str(getattr(setup, "rationale_text", "") or "").strip()
    return bool(rationale and not rationale.lower().startswith("rejected:"))


def _candles(rows: Iterable[Row], *, start: datetime) -> list[Candle]:
    return [
        Candle(
            open=row[0],
            high=row[1],
            low=row[2],
            close=row[3],
            volume=row[4],
            timestamp=start + timedelta(seconds=idx * 10),
        )
        for idx, row in enumerate(rows)
    ]


def _default_indicators() -> IndicatorSet:
    return IndicatorSet(
        ema9=10.18,
        ema20=10.05,
        ema200=9.70,
        vwap=10.12,
        macd_line=0.22,
        macd_signal=0.16,
        macd_histogram=0.06,
    )


def _default_levels() -> LevelSet:
    return LevelSet(
        premarket_high=10.30,
        premarket_low=9.70,
        hod=10.52,
        hod_source="RTH",
        lod=9.80,
        prior_close=9.90,
        vwap=10.12,
        resistance_levels=(10.20, 10.30),
        support_levels=(9.90, 10.05),
    )


def _micro_rows() -> list[Row]:
    return [
        (10.00, 10.08, 9.95, 10.06, 1200),
        (10.06, 10.22, 10.04, 10.20, 1800),
        (10.20, 10.36, 10.18, 10.34, 1700),
        (10.34, 10.36, 10.26, 10.28, 900),
        (10.28, 10.39, 10.27, 10.37, 1500),
    ]


def _flat_top_rows() -> list[Row]:
    return [
        (10.02, 10.18, 9.99, 10.14, 1000),
        (10.14, 10.19, 10.05, 10.16, 1050),
        (10.16, 10.20, 10.08, 10.17, 1020),
        (10.17, 10.19, 10.10, 10.18, 1100),
        (10.18, 10.30, 10.14, 10.27, 1600),
    ]


def _pmh_break_rows() -> list[Row]:
    return [
        (10.05, 10.16, 10.02, 10.12, 900),
        (10.12, 10.26, 10.08, 10.24, 1000),
        (10.24, 10.28, 10.18, 10.25, 950),
        (10.25, 10.31, 10.22, 10.29, 1000),
        (10.29, 10.44, 10.28, 10.38, 1800),
    ]


def _exhaustion_rows() -> list[Row]:
    return [
        (10.00, 10.10, 9.98, 10.05, 800),
        (10.05, 10.25, 10.03, 10.18, 900),
        (10.18, 10.55, 10.15, 10.45, 1100),
        (10.45, 10.95, 10.40, 10.86, 1300),
        (10.86, 11.90, 10.82, 11.45, 3200),
    ]


def _no_setup_rows() -> list[Row]:
    return [
        (10.40, 10.42, 10.20, 10.25, 1200),
        (10.25, 10.27, 10.08, 10.12, 1100),
        (10.12, 10.14, 9.98, 10.02, 1000),
        (10.02, 10.05, 9.90, 9.95, 950),
        (9.95, 10.00, 9.84, 9.90, 900),
    ]


def _missing_stop_result() -> PatternResult:
    return PatternResult(
        setup_id="P_PR6_MISSING_STOP",
        setup_family_id="MICRO_PULLBACK",
        pattern_name="PR6 Missing Stop",
        pattern_family=PatternFamily.PULLBACK,
        detected=True,
        direction=Direction.LONG,
        confidence=0.92,
        setup_quality_tags=["fixture_missing_stop"],
        entry_zone="Breakout trigger",
        trigger_level=10.40,
        stop_suggestion=None,
        stop_level=None,
        invalidation_level=None,
        rationale_text="Fixture setup has trigger evidence but no defensible stop.",
    )


def _indicator_only_result() -> PatternResult:
    return PatternResult(
        setup_id="P_PR6_INDICATOR_ONLY",
        setup_family_id="MICRO_PULLBACK",
        pattern_name="PR6 Indicator Only",
        pattern_family=PatternFamily.PULLBACK,
        detected=True,
        direction=Direction.LONG,
        confidence=0.91,
        setup_quality_tags=["indicator_only"],
        rationale_text="MACD and EMA are positive without price-action trigger.",
    )


@contextmanager
def _temporary_env(values: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
