from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.setup_engine.setup_families.breakouts import PremarketHighBreakPattern
from src.setup_engine.setup_families.momentum import MicroPullbackPattern
from src.setup_engine.setup_families.pullbacks import FlatTopBreakoutPattern, HODBreakPattern
from src.setup_engine.setup_families.ross_families import FirstPullbackPattern, ParabolicExhaustionPattern
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.decision_policy import IntentPolicyConfig, build_trade_intents
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluationSummary, PatternEvaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
    build_authoritative_pattern_inputs,
)
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.patterns.setup_fidelity import is_tradeable_entry_candidate
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult
from src.strategies.ross_momentum.policy import IndicatorProvenance, MissingDataBehavior
from src.strategies.strategy_contracts import SessionContext


def _candles(rows: list[tuple[float, float, float, float, float]], *, start: datetime | None = None) -> list[Candle]:
    base = start or datetime.now(timezone.utc) - timedelta(seconds=len(rows) * 10)
    return [
        Candle(open=o, high=h, low=l, close=c, volume=v, timestamp=base + timedelta(seconds=idx * 10))
        for idx, (o, h, l, c, v) in enumerate(rows)
    ]


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


def _levels(*, hod_source: str | None = "RTH") -> LevelSet:
    return LevelSet(
        premarket_high=10.30,
        premarket_low=9.70,
        hod=10.52,
        hod_source=hod_source,
        lod=9.80,
        prior_close=9.90,
        resistance_levels=(10.20, 10.30),
        support_levels=(9.90, 10.05),
    )


def _liquidity() -> LiquidityContext:
    return LiquidityContext(spread=0.01, float_millions=8.0, rvol=2.5, volume=400_000)


def _authoritative_inputs(
    *,
    rows: list[tuple[float, float, float, float, float]],
    session_label: str = "RTH_OPEN",
    stale_10s: bool = False,
    count_for_macd: bool = True,
    include_5m: bool = True,
) -> PatternInputs:
    now = datetime.now(timezone.utc)
    fresh_start = now - timedelta(seconds=len(rows) * 10)
    ten_second_start = now - timedelta(minutes=30) if stale_10s else fresh_start
    one_minute = _candles(rows, start=fresh_start)
    ten_second = _candles(rows, start=ten_second_start)
    five_minute = _candles(rows, start=fresh_start)
    if count_for_macd:
        pad = [(9.50 + idx * 0.01, 9.56 + idx * 0.01, 9.48 + idx * 0.01, 9.54 + idx * 0.01, 1000 + idx) for idx in range(26)]
        one_minute = _candles(pad + rows, start=now - timedelta(seconds=(len(pad) + len(rows)) * 10))
        five_minute = _candles(pad + rows, start=now - timedelta(seconds=(len(pad) + len(rows)) * 10))
    timeframe_candles = {"10s": ten_second, "1m": one_minute}
    if include_5m:
        timeframe_candles["5m"] = five_minute
    return build_authoritative_pattern_inputs(
        symbol="PR5",
        session_label=session_label,
        session_phase=session_label,
        timeframe_candles=timeframe_candles,
        indicators=IndicatorSet(ema9=10.18, ema20=10.05, ema200=9.70, vwap=10.12),
        levels=_levels(),
        liquidity_context=_liquidity(),
        news_context={"catalyst": "PRESENT", "session_phase": session_label, "macd": "0.2"},
        now=now,
    )


def _run_single(pattern, inputs: PatternInputs) -> PatternResult:
    registry = RossPatternRegistry()
    registry._patterns = [pattern]
    return registry.run(inputs)[0]


def test_micro_pullback_uses_pr4_timeframes_and_blocks_stale_opening_10s() -> None:
    inputs = _authoritative_inputs(rows=_micro_rows(), stale_10s=True)
    result = _run_single(MicroPullbackPattern(), inputs)

    assert inputs.timeframe_candles["10s"]
    assert inputs.timeframe_candles["1m"]
    assert inputs.timeframe_provenance["10s"] == IndicatorProvenance.STALE.value
    assert inputs.missing_data_actions["timeframe:10s"] == MissingDataBehavior.BLOCK.value
    assert result.detected is False
    assert result.rejection_reason and result.rejection_reason.startswith("pr4_input_block:MICRO_PULLBACK")


def test_orb_block_flag_does_not_suppress_micro_pullback_runtime() -> None:
    inputs = _authoritative_inputs(rows=_micro_rows(), include_5m=False)

    assert "PATTERN_INPUT_BLOCK_ORB_GAP_GO" in inputs.data_quality_flags
    assert inputs.setup_quality["ORB_GAP_GO"]["action"] == MissingDataBehavior.BLOCK.value
    assert inputs.setup_quality["MICRO_PULLBACK"]["action"] != MissingDataBehavior.BLOCK.value

    result = _run_single(MicroPullbackPattern(), inputs)

    assert result.detected is True
    assert result.rejection_reason is None
    assert result.setup_metadata["pr4_policy_setup"] == "MICRO_PULLBACK"


def test_orb_block_flag_is_scoped_for_other_setup_families() -> None:
    unrelated = [
        ("P_MICRO_PULLBACK", "MICRO_PULLBACK"),
        ("P_FIRST_PULLBACK", "FIRST_PULLBACK"),
        ("P_FLAT_TOP_BREAKOUT", "FLAT_TOP_BREAKOUT"),
        ("P_HOD_BREAK", "HOD_BREAK"),
        ("P_PREMARKET_HIGH_BREAK", "PREMARKET_HIGH_BREAK"),
    ]
    for setup_id, setup_family in unrelated:
        setup = PatternResult(
            setup_id=setup_id,
            setup_family_id=setup_family,
            pattern_name=setup_family,
            pattern_family=PatternFamily.BREAKOUT,
            detected=True,
            direction=Direction.LONG,
            confidence=0.75,
            setup_quality_tags=[],
            entry_zone="breakout",
            stop_suggestion="below structure",
            rationale_text="Valid price-action setup with scoped PR4 block elsewhere.",
            data_quality_flags=["PATTERN_INPUT_BLOCK_ORB_GAP_GO"],
            trigger_level=10.5,
            stop_level=10.0,
            invalidation_level=10.0,
        )
        assert is_tradeable_entry_candidate(setup) == (True, "ok")

    orb = PatternResult(
        setup_id="P_ORB",
        setup_family_id="OPENING_RANGE_BREAKOUT",
        pattern_name="Opening Range Breakout",
        pattern_family=PatternFamily.BREAKOUT,
        detected=True,
        direction=Direction.LONG,
        confidence=0.75,
        setup_quality_tags=[],
        entry_zone="breakout",
        stop_suggestion="below ORL",
        rationale_text="ORB setup with its own PR4 block.",
        data_quality_flags=["PATTERN_INPUT_BLOCK_ORB_GAP_GO"],
        trigger_level=10.5,
        stop_level=10.0,
        invalidation_level=10.0,
    )
    assert is_tradeable_entry_candidate(orb) == (False, "pr4_input_block_flag")


def test_first_pullback_requires_valid_structure_and_stop() -> None:
    valid = _run_single(FirstPullbackPattern(), _authoritative_inputs(rows=_first_pullback_rows(), session_label="RTH_MID"))
    assert valid.detected is True
    assert valid.trigger_level is not None
    assert valid.stop_level is not None
    assert valid.rationale_text

    bad_rows = _first_pullback_rows()
    bad_rows[-2] = (10.36, 10.43, 10.32, 10.41, 850)
    invalid = _run_single(FirstPullbackPattern(), _authoritative_inputs(rows=bad_rows, session_label="RTH_MID"))
    assert invalid.detected is False
    assert invalid.rejection_reason in {"pullback bars not controlled", "no reclaim trigger"}


def test_flat_top_breakout_uses_real_resistance_and_volume_confirmation() -> None:
    rows = [
        (10.02, 10.18, 9.99, 10.14, 1000),
        (10.14, 10.19, 10.05, 10.16, 1050),
        (10.16, 10.20, 10.08, 10.17, 1020),
        (10.17, 10.19, 10.10, 10.18, 1100),
        (10.18, 10.30, 10.14, 10.27, 1600),
    ]
    detected = _run_single(FlatTopBreakoutPattern(), _authoritative_inputs(rows=rows, session_label="RTH_MID"))
    assert detected.detected is True
    assert detected.trigger_level == 10.20
    assert detected.stop_level is not None

    weak_volume = rows[:-1] + [(10.18, 10.30, 10.14, 10.27, 600)]
    rejected = _run_single(FlatTopBreakoutPattern(), _authoritative_inputs(rows=weak_volume, session_label="RTH_MID"))
    assert rejected.detected is False
    assert rejected.rejection_reason == "breakout_volume_below_average"


def test_hod_and_pmh_breaks_require_valid_levels() -> None:
    hod_missing = PatternInputs(
        symbol="PR5HOD",
        timeframe="1m",
        candles=_candles([(10.2, 10.3, 10.1, 10.25, 1000)] * 6),
        session_context=SessionContext.REGULAR,
        levels=LevelSet(hod=None, hod_source="RTH"),
        indicators=IndicatorSet(ema9=10.2, ema20=10.1, vwap=10.15),
        liquidity_context=_liquidity(),
    )
    assert _run_single(HODBreakPattern(), hod_missing).rejection_reason == "missing_hod"

    pmh_missing = PatternInputs(
        symbol="PR5PMH",
        timeframe="1m",
        candles=_candles([(10.2, 10.3, 10.1, 10.25, 1000), (10.25, 10.36, 10.2, 10.34, 1600)]),
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=None),
        indicators=IndicatorSet(ema9=10.2, ema20=10.1, vwap=10.15),
        liquidity_context=_liquidity(),
    )
    assert _run_single(PremarketHighBreakPattern(), pmh_missing).rejection_reason == "missing_premarket_high"


def test_exhaustion_detected_but_not_selected_as_long_entry(capsys) -> None:
    inputs = PatternInputs(
        symbol="PR5EX",
        timeframe="1m",
        candles=_candles(
            [
                (10.0, 10.1, 9.98, 10.05, 800),
                (10.05, 10.25, 10.03, 10.18, 900),
                (10.18, 10.55, 10.15, 10.45, 1100),
                (10.45, 10.95, 10.4, 10.86, 1300),
                (10.86, 11.9, 10.82, 11.45, 3200),
            ]
        ),
        session_context=SessionContext.REGULAR,
        levels=_levels(),
        indicators=IndicatorSet(ema9=10.5, ema20=10.25, vwap=10.9),
        liquidity_context=_liquidity(),
    )
    evaluator = PatternEvaluator(RossPatternRegistry())
    evaluator._registry._patterns = [ParabolicExhaustionPattern()]

    summary = evaluator.evaluate([inputs])

    assert any(result.detected and result.non_entry_signal for result in summary.all_results)
    assert summary.best_long_setup is None
    assert "[ROSS][DECISION][RISK_OFF]" in capsys.readouterr().out


def test_missing_macd_degrades_abcd_without_blocking_micro_pullback() -> None:
    inputs = _authoritative_inputs(rows=_micro_rows(), session_label="RTH_MID", count_for_macd=False)
    assert inputs.indicator_provenance["macd_line"] == IndicatorProvenance.MISSING.value
    assert inputs.setup_quality["ABCD_CONTINUATION"]["action"] == MissingDataBehavior.DEGRADE.value
    assert inputs.setup_quality["MICRO_PULLBACK"]["indicator_provenance"]["macd_line"] == IndicatorProvenance.NOT_REQUIRED_FOR_SETUP.value

    result = _run_single(MicroPullbackPattern(), inputs)
    assert result.rejection_reason != "pr4_input_block:ABCD_CONTINUATION"


def _summary_with(setup) -> PatternEvaluationSummary:
    return PatternEvaluationSummary(
        all_results=[setup],
        best_long_setup=setup,
        best_short_setup=None,
        conflict_flag=False,
        combined_rationale_text="test",
        veto_flags=[],
    )


def test_indicator_only_setup_cannot_create_trade_intent(capsys) -> None:
    setup = SimpleNamespace(
        detected=True,
        confidence=0.95,
        direction=Direction.LONG,
        pattern_name="Indicator Only",
        entry_zone=None,
        trigger_level=None,
        stop_suggestion=None,
        stop_level=None,
        invalidation_level=None,
        target_suggestion=None,
        rationale_text="MACD and EMA are positive but no price-action trigger.",
        risk_flags=[],
        data_quality_flags=[],
    )

    intents = build_trade_intents("RossMomentumStrategyV1", "PR5IO", _summary_with(setup), config=IntentPolicyConfig(min_confidence=0.6), trigger_ready_now=True)

    assert intents == []
    output = capsys.readouterr().out
    assert "[ROSS][SETUP][DROP] symbol=PR5IO setup=Indicator Only reason=missing_trigger" in output
    assert "[ROSS][DECISION][NO_TRADE] symbol=PR5IO reason=no_valid_setup" in output
    assert "outcome=CREATED" not in output


def test_detected_setup_without_stop_is_dropped_before_intent(capsys) -> None:
    setup = SimpleNamespace(
        detected=True,
        confidence=0.95,
        direction=Direction.LONG,
        pattern_name="No Stop",
        entry_zone="breakout",
        trigger_level=10.5,
        stop_suggestion=None,
        stop_level=None,
        invalidation_level=None,
        target_suggestion=None,
        rationale_text="Breakout exists but no defensible stop.",
        risk_flags=[],
        data_quality_flags=[],
    )

    intents = build_trade_intents("RossMomentumStrategyV1", "PR5STOP", _summary_with(setup), config=IntentPolicyConfig(min_confidence=0.6), trigger_ready_now=True)

    assert intents == []
    assert "reason=missing_stop" in capsys.readouterr().out


class _InvalidRegistry:
    def run(self, inputs, **kwargs):
        return [
            PatternResult(
                setup_id="P_FAKE",
                pattern_name="Fake Indicator",
                pattern_family=PatternFamily.BREAKOUT,
                detected=True,
                direction=Direction.LONG,
                confidence=0.99,
                setup_quality_tags=["indicator_only"],
                rationale_text="RSI crossed up without price-action structure.",
            )
        ]


def test_no_valid_setup_emits_no_trade_diagnostics_not_fallback_intent(capsys) -> None:
    inputs = PatternInputs(
        symbol="PR5NONE",
        timeframe="1m",
        candles=_candles(_micro_rows()),
        session_context=SessionContext.REGULAR,
        levels=_levels(),
        indicators=IndicatorSet(ema9=10.2, ema20=10.1, vwap=10.15),
        liquidity_context=_liquidity(),
    )

    summary = PatternEvaluator(_InvalidRegistry()).evaluate([inputs])

    assert summary.best_long_setup is None
    output = capsys.readouterr().out
    assert "[ROSS][SETUP][DROP] symbol=PR5NONE pattern=Fake Indicator reason=missing_trigger" in output
    assert "[ROSS][DECISION][NO_TRADE] reason=no_valid_setup" in output
    assert "[ROSS][FORCED_TRIGGER]" not in output
