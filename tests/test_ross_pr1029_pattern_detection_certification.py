from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.setup_engine.registry import build_tradeable_patterns
from src.setup_engine.setup_families.breakouts import OpeningRangeBreakoutPattern, PremarketHighBreakPattern
from src.setup_engine.setup_families.momentum import BullFlagPattern, MicroPullbackPattern
from src.setup_engine.setup_families.pullbacks import (
    EmaPullbackPattern,
    FlatTopBreakoutPattern,
    HODBreakPattern,
    OpeningDrivePattern,
    TrendContinuationStairStepPattern,
    VwapPullbackPattern,
)
from src.setup_engine.setup_families.ross_families import (
    ABCDPattern,
    FailedOrbFakeoutPattern,
    FirstPullbackPattern,
    GapGoPattern,
    HaltResumePattern,
    ParabolicExhaustionPattern,
)
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.decision_policy import IntentPolicyConfig, build_trade_intents
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluationSummary
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.ross_momentum.patterns.pattern_registry import (
    RossPatternRegistry,
    build_additional_heuristic_patterns,
)
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.ross_momentum.patterns.setup_fidelity import is_tradeable_entry_candidate
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]], *, start: datetime | None = None) -> list[Candle]:
    base = start or datetime.now(timezone.utc) - timedelta(seconds=len(rows) * 10)
    return [
        Candle(open=o, high=h, low=l, close=c, volume=v, timestamp=base + timedelta(seconds=idx * 10))
        for idx, (o, h, l, c, v) in enumerate(rows)
    ]


def _levels(
    *,
    pmh: float | None = 10.30,
    hod: float | None = 10.52,
    hod_source: str | None = "RTH",
    prior_close: float | None = 9.90,
    opening_range_high: float | None = 10.20,
    opening_range_low: float | None = 9.95,
) -> LevelSet:
    key_levels: dict[str, float] = {}
    if pmh is not None:
        key_levels["PREMARKET_HIGH"] = pmh
    if hod is not None:
        key_levels["HOD"] = hod
    if prior_close is not None:
        key_levels["PRIOR_CLOSE"] = prior_close
    if opening_range_high is not None:
        key_levels["OPENING_RANGE_HIGH"] = opening_range_high
    if opening_range_low is not None:
        key_levels["OPENING_RANGE_LOW"] = opening_range_low
    return LevelSet(
        premarket_high=pmh,
        premarket_low=9.70,
        hod=hod,
        hod_source=hod_source,
        lod=9.80,
        prior_close=prior_close,
        resistance_levels=tuple(level for level in (pmh, hod, opening_range_high) if level is not None),
        support_levels=(9.90, 10.05),
        key_levels=key_levels,
    )


def _liquidity(*, rvol: float | None = 2.5, spread: float | None = 0.005) -> LiquidityContext:
    return LiquidityContext(spread=spread, float_millions=8.0, rvol=rvol, volume=400_000)


def _indicators(
    *,
    ema9: float | None = 10.18,
    ema20: float | None = 10.05,
    vwap: float | None = 10.12,
) -> IndicatorSet:
    return IndicatorSet(
        ema9=ema9,
        ema20=ema20,
        ema200=9.70,
        vwap=vwap,
        ema9_prev=(ema9 - 0.05) if ema9 is not None else None,
        ema20_prev=(ema20 - 0.02) if ema20 is not None else None,
    )


def _inputs(
    *,
    symbol: str,
    rows: list[tuple[float, float, float, float, float]],
    session: SessionContext = SessionContext.REGULAR,
    levels: LevelSet | None = None,
    indicators: IndicatorSet | None = None,
    liquidity: LiquidityContext | None = None,
    news_context: dict[str, str] | None = None,
    session_phase: str | None = None,
) -> PatternInputs:
    context = {"catalyst": "PRESENT", "macd": "0.2"}
    if news_context is not None:
        context = dict(news_context)
    if session_phase is not None:
        context.setdefault("session_phase", session_phase)
    return PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=_candles(rows),
        session_context=session,
        levels=levels or _levels(),
        indicators=indicators or _indicators(),
        liquidity_context=liquidity or _liquidity(),
        news_context=context,
        session_phase=session_phase,
    )


def _run_single(pattern, inputs: PatternInputs) -> PatternResult:
    registry = RossPatternRegistry()
    registry._patterns = [pattern]
    return registry.run(inputs)[0]


def _micro_rows() -> list[tuple[float, float, float, float, float]]:
    return [
        (10.00, 10.08, 9.95, 10.06, 1200),
        (10.06, 10.22, 10.04, 10.20, 1800),
        (10.20, 10.36, 10.18, 10.34, 1700),
        (10.34, 10.36, 10.26, 10.28, 900),
        (10.28, 10.39, 10.27, 10.37, 1500),
    ]


def _first_pullback_rows() -> list[tuple[float, float, float, float, float]]:
    return [
        (10.00, 10.05, 9.95, 10.02, 1000),
        (10.02, 10.22, 10.00, 10.20, 1400),
        (10.20, 10.48, 10.18, 10.45, 1700),
        (10.45, 10.46, 10.32, 10.36, 900),
        (10.36, 10.37, 10.28, 10.30, 850),
        (10.30, 10.52, 10.29, 10.49, 1800),
    ]


def _flat_top_rows() -> list[tuple[float, float, float, float, float]]:
    return [
        (10.02, 10.18, 9.99, 10.14, 1000),
        (10.14, 10.19, 10.05, 10.16, 1050),
        (10.16, 10.20, 10.08, 10.17, 1020),
        (10.17, 10.19, 10.10, 10.18, 1100),
        (10.18, 10.30, 10.14, 10.27, 1600),
    ]


def _hod_rows() -> list[tuple[float, float, float, float, float]]:
    return [
        (10.33, 10.42, 10.30, 10.40, 900),
        (10.40, 10.49, 10.38, 10.46, 1000),
        (10.46, 10.50, 10.43, 10.48, 950),
        (10.48, 10.51, 10.45, 10.49, 980),
        (10.49, 10.52, 10.46, 10.50, 970),
        (10.48, 10.515, 10.47, 10.51, 1400),
    ]


def _pmh_rows() -> list[tuple[float, float, float, float, float]]:
    return [
        (10.15, 10.22, 10.10, 10.20, 800),
        (10.20, 10.28, 10.16, 10.25, 850),
        (10.25, 10.34, 10.22, 10.32, 1500),
    ]


def test_pr1029_pullback_and_breakout_families_have_positive_negative_fixtures() -> None:
    micro = _run_single(MicroPullbackPattern(), _inputs(symbol="PR29MP", rows=_micro_rows()))
    assert micro.detected is True
    assert micro.rejection_reason is None
    micro_missing_ema = _run_single(
        MicroPullbackPattern(),
        _inputs(symbol="PR29MPB", rows=_micro_rows(), indicators=_indicators(ema9=10.50)),
    )
    assert micro_missing_ema.detected is False
    assert micro_missing_ema.rejection_reason == "price below EMA9"

    first_pullback = _run_single(FirstPullbackPattern(), _inputs(symbol="PR29FP", rows=_first_pullback_rows()))
    assert first_pullback.detected is True
    assert first_pullback.trigger_level is not None
    assert first_pullback.stop_level is not None
    first_bad_rows = _first_pullback_rows()
    first_bad_rows[-2] = (10.36, 10.43, 10.32, 10.41, 850)
    first_rejected = _run_single(FirstPullbackPattern(), _inputs(symbol="PR29FPB", rows=first_bad_rows))
    assert first_rejected.detected is False
    assert first_rejected.rejection_reason in {"pullback bars not controlled", "no reclaim trigger"}

    flat = _run_single(FlatTopBreakoutPattern(), _inputs(symbol="PR29FT", rows=_flat_top_rows()))
    assert flat.detected is True
    assert flat.trigger_level == 10.20
    assert flat.stop_level is not None
    weak_flat_rows = _flat_top_rows()[:-1] + [(10.18, 10.30, 10.14, 10.27, 600)]
    weak_flat = _run_single(FlatTopBreakoutPattern(), _inputs(symbol="PR29FTB", rows=weak_flat_rows))
    assert weak_flat.detected is False
    assert weak_flat.rejection_reason == "breakout_volume_below_average"

    hod = _run_single(
        HODBreakPattern(),
        _inputs(
            symbol="PR29HOD",
            rows=_hod_rows(),
            levels=_levels(hod=10.52, hod_source="RTH"),
            indicators=_indicators(ema9=10.45, ema20=10.35, vwap=10.40),
        ),
    )
    assert hod.detected is True
    assert hod.trigger_level == 10.52
    assert hod.stop_level is not None
    bad_hod = _run_single(
        HODBreakPattern(),
        _inputs(symbol="PR29HODB", rows=_hod_rows(), levels=_levels(hod=10.52, hod_source="PREMARKET")),
    )
    assert bad_hod.detected is False
    assert bad_hod.rejection_reason == "invalid_hod_source"

    pmh = _run_single(
        PremarketHighBreakPattern(),
        _inputs(symbol="PR29PMH", rows=_pmh_rows(), session=SessionContext.PRE, levels=_levels(pmh=10.30)),
    )
    assert pmh.detected is True
    assert pmh.trigger_level == 10.30
    assert pmh.stop_level is not None
    missing_pmh = _run_single(
        PremarketHighBreakPattern(),
        _inputs(symbol="PR29PMHB", rows=_pmh_rows(), session=SessionContext.PRE, levels=_levels(pmh=None)),
    )
    assert missing_pmh.detected is False
    assert missing_pmh.rejection_reason == "missing_premarket_high"


def test_pr1029_indicator_context_requires_price_action_not_standalone_authority() -> None:
    ema_rows = [
        (10.00, 10.10, 9.98, 10.08, 1500),
        (10.08, 10.35, 10.06, 10.32, 1800),
        (10.32, 10.58, 10.30, 10.55, 1700),
        (10.55, 10.62, 10.50, 10.58, 1600),
        (10.58, 10.60, 10.38, 10.40, 700),
        (10.40, 10.54, 10.39, 10.50, 1300),
    ]
    ema = _run_single(
        EmaPullbackPattern(),
        _inputs(symbol="PR29EMA", rows=ema_rows, indicators=_indicators(ema9=10.42, ema20=10.30, vwap=10.25)),
    )
    assert ema.detected is True
    assert ema.trigger_level is not None
    assert ema.stop_level is not None
    missing_ema = _run_single(
        EmaPullbackPattern(),
        _inputs(symbol="PR29EMAB", rows=ema_rows, indicators=_indicators(ema9=None, ema20=10.30, vwap=10.25)),
    )
    assert missing_ema.detected is False
    assert missing_ema.rejection_reason == "missing_ema"

    vwap_rows = [
        (10.00, 10.12, 9.98, 10.08, 1500),
        (10.08, 10.35, 10.06, 10.32, 1800),
        (10.32, 10.62, 10.30, 10.58, 1700),
        (10.58, 10.64, 10.50, 10.60, 1600),
        (10.60, 10.62, 10.37, 10.39, 700),
        (10.39, 10.56, 10.40, 10.52, 1300),
    ]
    vwap = _run_single(
        VwapPullbackPattern(),
        _inputs(symbol="PR29VWAP", rows=vwap_rows, indicators=_indicators(ema9=10.45, ema20=10.25, vwap=10.40)),
    )
    assert vwap.detected is True
    assert vwap.trigger_level is not None
    assert vwap.stop_level is not None
    missing_vwap = _run_single(
        VwapPullbackPattern(),
        _inputs(symbol="PR29VWAPB", rows=vwap_rows, indicators=_indicators(ema9=10.45, ema20=10.25, vwap=None)),
    )
    assert missing_vwap.detected is False
    assert missing_vwap.rejection_reason == "missing_vwap"

    indicator_only = SimpleNamespace(
        detected=True,
        confidence=0.99,
        direction=Direction.LONG,
        pattern_name="Indicator Only",
        entry_zone=None,
        trigger_level=None,
        stop_suggestion=None,
        stop_level=None,
        invalidation_level=None,
        target_suggestion=None,
        rationale_text="VWAP, EMA, and MACD are aligned without a price-action setup.",
        risk_flags=[],
        data_quality_flags=[],
    )
    summary = PatternEvaluationSummary(
        all_results=[indicator_only],
        best_long_setup=indicator_only,
        best_short_setup=None,
        conflict_flag=False,
        combined_rationale_text="test",
        veto_flags=[],
    )
    intents = build_trade_intents(
        "RossMomentumStrategyV1",
        "PR29IO",
        summary,
        config=IntentPolicyConfig(min_confidence=0.6),
        trigger_ready_now=True,
    )
    assert intents == []


def test_pr1029_remaining_continuation_families_have_fixture_evidence() -> None:
    bull_flag_rows = [
        (10.00, 10.32, 9.98, 10.30, 1800),
        (10.30, 10.65, 10.28, 10.62, 1900),
        (10.62, 10.95, 10.60, 10.90, 1850),
        (10.90, 10.92, 10.72, 10.80, 900),
        (10.80, 10.88, 10.70, 10.76, 850),
        (10.76, 10.84, 10.68, 10.74, 800),
        (10.74, 10.80, 10.66, 10.72, 760),
        (10.72, 10.78, 10.65, 10.73, 740),
        (10.73, 11.06, 10.72, 11.00, 1700),
    ]
    bull_flag = _run_single(
        BullFlagPattern(),
        _inputs(symbol="PR29FLAG", rows=bull_flag_rows, indicators=_indicators(ema9=10.70, ema20=10.40, vwap=10.35)),
    )
    assert bull_flag.detected is True
    assert bull_flag.trigger_level is not None
    assert bull_flag.stop_level is not None
    no_break_flag = _run_single(
        BullFlagPattern(),
        _inputs(symbol="PR29FLAGB", rows=bull_flag_rows[:-1] + [(10.73, 10.90, 10.72, 10.88, 1700)]),
    )
    assert no_break_flag.detected is False
    assert no_break_flag.rejection_reason == "no breakout close"

    abcd_rows = [
        (10.10, 10.20, 10.00, 10.15, 1000),
        (10.15, 10.25, 9.90, 10.20, 1100),
        (10.20, 10.55, 10.10, 10.50, 1500),
        (10.50, 10.80, 10.45, 10.75, 1600),
        (10.75, 10.78, 10.45, 10.50, 900),
        (10.50, 10.55, 10.30, 10.40, 850),
        (10.40, 10.60, 10.38, 10.55, 1000),
        (10.55, 10.70, 10.50, 10.65, 1200),
    ]
    abcd = _run_single(ABCDPattern(), _inputs(symbol="PR29ABCD", rows=abcd_rows))
    assert abcd.detected is True
    assert abcd.trigger_level is not None
    assert abcd.stop_level is not None
    flat_abcd = _run_single(ABCDPattern(), _inputs(symbol="PR29ABCDB", rows=[(10.0, 10.05, 9.98, 10.02, 1000)] * 7))
    assert flat_abcd.detected is False
    assert flat_abcd.rejection_reason == "NO_SWING_SEQUENCE"

    orb_rows = [
        (10.00, 10.10, 9.98, 10.05, 900),
        (10.05, 10.14, 10.02, 10.10, 950),
        (10.10, 10.18, 10.05, 10.15, 1000),
        (10.15, 10.20, 10.09, 10.18, 1050),
        (10.18, 10.21, 10.12, 10.19, 1100),
        (10.19, 10.32, 10.18, 10.28, 2100),
    ]
    orb = _run_single(
        OpeningRangeBreakoutPattern(),
        _inputs(
            symbol="PR29ORB",
            rows=orb_rows,
            levels=_levels(pmh=10.25, opening_range_high=10.20, opening_range_low=10.02),
            indicators=_indicators(ema9=10.18, ema20=10.08, vwap=10.10),
            session_phase="RTH_OPEN",
        ),
    )
    assert orb.detected is True
    assert orb.trigger_level == 10.20
    missing_macd_orb = _run_single(
        OpeningRangeBreakoutPattern(),
        _inputs(
            symbol="PR29ORBB",
            rows=orb_rows,
            levels=_levels(pmh=10.25, opening_range_high=10.20, opening_range_low=10.02),
            indicators=_indicators(ema9=10.18, ema20=10.08, vwap=10.10),
            news_context={"catalyst": "PRESENT", "session_phase": "RTH_OPEN"},
            session_phase="RTH_OPEN",
        ),
    )
    assert missing_macd_orb.detected is False
    assert missing_macd_orb.rejection_reason == "missing_macd"

    opening_drive_rows = [
        (10.00, 10.12, 9.98, 10.10, 900),
        (10.10, 10.22, 10.08, 10.20, 950),
        (10.20, 10.34, 10.18, 10.30, 1000),
        (10.30, 10.38, 10.25, 10.34, 1000),
        (10.34, 10.45, 10.32, 10.42, 1600),
    ]
    opening_drive = _run_single(
        OpeningDrivePattern(),
        _inputs(symbol="PR29OD", rows=opening_drive_rows, session_phase="RTH_OPEN"),
    )
    assert opening_drive.detected is True
    assert opening_drive.stop_level is not None
    bad_opening_drive = _run_single(
        OpeningDrivePattern(),
        _inputs(symbol="PR29ODB", rows=opening_drive_rows, session_phase="RTH_MID"),
    )
    assert bad_opening_drive.detected is False
    assert bad_opening_drive.rejection_reason == "invalid_phase"

    gap_go_rows = [
        (10.05, 10.18, 10.00, 10.14, 1200),
        (10.14, 10.30, 10.10, 10.28, 1400),
        (10.28, 10.48, 10.20, 10.42, 1500),
        (10.42, 10.55, 10.35, 10.50, 1800),
    ]
    gap_go = _run_single(
        GapGoPattern(),
        _inputs(
            symbol="PR29GAP",
            rows=gap_go_rows,
            levels=_levels(pmh=10.30, hod=10.45, prior_close=9.80),
            news_context={"trend_up": "true", "impulse_active": "true", "macd": "0.2"},
        ),
    )
    assert gap_go.detected is True
    assert gap_go.trigger_type in {"PMH_BREAK", "HOD_BREAK", "BREAK_AND_HOLD", "BREAKOUT_HIGH"}
    no_gap = _run_single(
        GapGoPattern(),
        _inputs(symbol="PR29GAPB", rows=gap_go_rows, levels=_levels(pmh=10.30, hod=10.45, prior_close=None)),
    )
    assert no_gap.detected is False
    assert no_gap.rejection_reason == "INSUFFICIENT_GAP"

    stair_rows = [
        (10.00, 10.20, 9.95, 10.15, 1500),
        (10.15, 10.42, 10.10, 10.38, 1700),
        (10.38, 10.62, 10.30, 10.55, 1600),
        (10.55, 10.78, 10.46, 10.68, 1500),
        (10.68, 10.74, 10.58, 10.62, 700),
        (10.62, 10.82, 10.60, 10.78, 1200),
    ]
    stair = _run_single(
        TrendContinuationStairStepPattern(),
        _inputs(symbol="PR29STAIR", rows=stair_rows, indicators=_indicators(ema9=10.55, ema20=10.30, vwap=10.20)),
    )
    assert stair.detected is True
    assert stair.trigger_level is not None
    low_rvol_stair = _run_single(
        TrendContinuationStairStepPattern(),
        _inputs(symbol="PR29STAIRB", rows=stair_rows, liquidity=_liquidity(rvol=0.1)),
    )
    assert low_rvol_stair.detected is False
    assert low_rvol_stair.rejection_reason == "invalid_inputs"


def test_pr1029_reversal_halt_and_placeholder_paths_cannot_create_long_trade_authority() -> None:
    exhaustion_inputs = _inputs(
        symbol="PR29EX",
        rows=[
            (10.0, 10.1, 9.98, 10.05, 800),
            (10.05, 10.25, 10.03, 10.18, 900),
            (10.18, 10.55, 10.15, 10.45, 1100),
            (10.45, 10.95, 10.4, 10.86, 1300),
            (10.86, 11.9, 10.82, 11.45, 3200),
        ],
        indicators=_indicators(ema9=10.5, ema20=10.25, vwap=10.9),
    )
    exhaustion = ParabolicExhaustionPattern().evaluate(exhaustion_inputs)
    assert exhaustion.detected is True
    assert exhaustion.non_entry_signal is True
    assert is_tradeable_entry_candidate(exhaustion) == (False, "risk_off_non_entry")

    failed_orb_inputs = _inputs(
        symbol="PR29FAILORB",
        rows=[
            (10.00, 10.10, 9.95, 10.05, 900),
            (10.05, 10.16, 10.01, 10.10, 950),
            (10.10, 10.20, 10.05, 10.18, 1000),
            (10.18, 10.19, 10.08, 10.12, 950),
            (10.12, 10.18, 10.02, 10.10, 900),
            (10.10, 10.34, 10.07, 10.22, 1300),
            (10.22, 10.24, 10.08, 10.15, 1200),
        ],
    )
    failed_orb = FailedOrbFakeoutPattern().evaluate(failed_orb_inputs)
    assert failed_orb.detected is True
    assert failed_orb.direction == Direction.SHORT
    assert is_tradeable_entry_candidate(failed_orb) == (False, "non_long_setup")

    halt = _run_single(HaltResumePattern(), _inputs(symbol="PR29HALT", rows=_micro_rows()))
    assert halt.detected is False
    assert halt.rejection_reason == "disabled_no_halt_tape_in_pattern_inputs"

    tradeable_patterns = build_tradeable_patterns()
    assert tradeable_patterns
    assert all(not bool(getattr(pattern, "is_placeholder", False)) for pattern in tradeable_patterns)
    assert build_additional_heuristic_patterns() == []

    registry = RossPatternRegistry()
    placeholder_ids = registry.inactive_pattern_ids
    assert {
        "C_ENGULFING",
        "C_LONG_UPPER_WICK",
        "C_MARUBOZU",
        "C_THREE_SOLDIERS_CROWS",
        "P_CLIMAX_TOP",
        "P_VOLUME_CLIMAX",
    }.issubset(placeholder_ids)
    placeholder_results = {
        result.setup_id: result
        for result in registry.run(_inputs(symbol="PR29REG", rows=_micro_rows()))
        if result.setup_id in placeholder_ids
    }
    assert placeholder_results.keys() == placeholder_ids
    assert all(result.detected is False for result in placeholder_results.values())
