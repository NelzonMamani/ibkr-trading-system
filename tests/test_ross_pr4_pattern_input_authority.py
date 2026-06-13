from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.domain.market_snapshot import MarketSnapshot
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    build_authoritative_pattern_inputs,
)
from src.strategies.ross_momentum.patterns.pattern_trace import build_runtime_pattern_inputs
from src.strategies.ross_momentum.policy import (
    IndicatorProvenance,
    MissingDataBehavior,
    PatternInputPolicy,
)


def _candles(count: int, *, start: float = 10.0, step: float = 0.03, timestamp_start: datetime | None = None) -> list[Candle]:
    base_ts = timestamp_start or datetime(2026, 6, 13, 13, 30, tzinfo=timezone.utc)
    rows: list[Candle] = []
    for idx in range(count):
        value = start + (idx * step)
        rows.append(
            Candle(
                open=value,
                high=value + 0.05,
                low=value - 0.04,
                close=value + 0.02,
                volume=10_000 + idx,
                timestamp=base_ts + timedelta(seconds=10 * idx),
            )
        )
    return rows


def _levels() -> LevelSet:
    return LevelSet(
        premarket_high=10.7,
        premarket_low=9.8,
        prior_close=9.5,
        support_levels=(9.8, 10.0),
        resistance_levels=(10.7, 11.0),
    )


def _liquidity() -> LiquidityContext:
    return LiquidityContext(spread=0.02, float_millions=8.0, rvol=5.2, volume=1_500_000)


def test_policy_defines_ross_timeframes_and_setup_requirements() -> None:
    policy = PatternInputPolicy.from_policy_v2()

    assert policy.required_timeframes == ("1m",)
    assert policy.preferred_timeframes == ("10s", "1m", "5m")
    assert policy.plan_for_session("RTH_OPEN").execution_refinement_timeframe == "10s"
    assert policy.plan_for_session("RTH_MID").execution_refinement_timeframe == "1m"
    assert policy.requirement_for_setup("MICRO_PULLBACK").behavior_for("timeframe:10s") == MissingDataBehavior.BLOCK
    assert policy.requirement_for_setup("ABCD_CONTINUATION").behavior_for("macd_line") == MissingDataBehavior.DEGRADE


def test_builder_preserves_10s_1m_5m_inputs_and_logs_traceability(capsys) -> None:
    inputs = build_authoritative_pattern_inputs(
        symbol="PR4X",
        session_label="RTH_OPEN",
        timeframe_candles={"10s": _candles(30), "1m": _candles(30), "5m": _candles(30)},
        levels=_levels(),
        liquidity_context=_liquidity(),
        news_context={"catalyst": "contract"},
    )
    output = capsys.readouterr().out

    assert set(inputs.timeframe_candles) == {"10s", "1m", "5m"}
    assert inputs.timeframe == "1m"
    assert inputs.primary_timeframe == "1m"
    assert inputs.execution_refinement_timeframe == "10s"
    assert inputs.context_timeframe == "5m"
    assert len(inputs.candles) == 30
    assert inputs.timeframe_provenance["10s"] == IndicatorProvenance.PRESENT.value
    assert inputs.timeframe_provenance["1m"] == IndicatorProvenance.PRESENT.value
    assert inputs.timeframe_provenance["5m"] == IndicatorProvenance.PRESENT.value
    assert "[ROSS][PATTERN_INPUT][BUILD]" in output
    assert "[ROSS][PATTERN_INPUT][TIMEFRAMES]" in output
    assert "[ROSS][PATTERN_INPUT][INDICATORS]" in output
    assert "[ROSS][PATTERN_INPUT][LEVELS]" in output
    assert "[ROSS][PATTERN_INPUT][MISSING]" in output
    assert "[ROSS][PATTERN_INPUT][QUALITY]" in output


def test_runtime_builder_feeds_authoritative_10s_1m_5m_inputs(monkeypatch) -> None:
    by_timeframe = {
        "10s": _candles(30, start=10.0),
        "1m": _candles(30, start=10.2),
        "5m": _candles(30, start=10.4),
    }

    def fake_get_intraday_bars(**kwargs):
        return by_timeframe[str(kwargs["timeframe"])]

    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        fake_get_intraday_bars,
    )

    inputs, flags = build_runtime_pattern_inputs(
        symbol="RUNTIME4",
        row={
            "symbol": "RUNTIME4",
            "session_label": "RTH_OPEN",
            "last_price": 10.8,
            "bid": 10.79,
            "ask": 10.81,
            "spread": 0.02,
            "volume": 120_000,
            "pct_change": 8.5,
            "rvol": 6.0,
            "float_millions": 8.0,
            "prior_close": 9.9,
        },
        snapshot=MarketSnapshot(
            symbol="RUNTIME4",
            bid=10.79,
            ask=10.81,
            last=10.8,
            volume=120_000,
            asof_utc=datetime.now(timezone.utc),
        ),
        session_label="RTH_OPEN",
        session_phase="RTH_OPEN",
    )

    assert inputs is not None
    assert flags == []
    assert set(inputs.timeframe_candles) == {"10s", "1m", "5m"}
    assert inputs.primary_timeframe == "1m"
    assert inputs.execution_refinement_timeframe == "10s"
    assert inputs.context_timeframe == "5m"
    # Runtime construction uses current UTC, so these fixed fixture timestamps
    # are stale once they exceed the policy freshness windows.
    assert inputs.timeframe_provenance["10s"] == IndicatorProvenance.STALE.value
    assert inputs.timeframe_provenance["1m"] == IndicatorProvenance.STALE.value
    assert inputs.timeframe_provenance["5m"] == IndicatorProvenance.STALE.value
    assert inputs.liquidity_context.volume == 120_000


def test_runtime_builder_marks_stale_opening_10s_as_block(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    by_timeframe = {
        "10s": _candles(30, timestamp_start=now - timedelta(minutes=30)),
        "1m": _candles(30, timestamp_start=now - timedelta(minutes=5)),
        "5m": _candles(30, timestamp_start=now - timedelta(minutes=5)),
    }

    def fake_get_intraday_bars(**kwargs):
        return by_timeframe[str(kwargs["timeframe"])]

    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        fake_get_intraday_bars,
    )

    inputs, _flags = build_runtime_pattern_inputs(
        symbol="STALE10",
        row={
            "symbol": "STALE10",
            "session_label": "RTH_OPEN",
            "last_price": 10.8,
            "bid": 10.79,
            "ask": 10.81,
            "spread": 0.02,
            "volume": 120_000,
            "pct_change": 8.5,
            "rvol": 6.0,
            "float_millions": 8.0,
            "prior_close": 9.9,
        },
        snapshot=MarketSnapshot(
            symbol="STALE10",
            bid=10.79,
            ask=10.81,
            last=10.8,
            volume=120_000,
            asof_utc=now,
        ),
        session_label="RTH_OPEN",
        session_phase="RTH_OPEN",
    )

    assert inputs is not None
    assert inputs.timeframe_provenance["10s"] == IndicatorProvenance.STALE.value
    assert inputs.missing_data_actions["timeframe:10s"] == MissingDataBehavior.BLOCK.value
    assert inputs.setup_quality["MICRO_PULLBACK"]["action"] == MissingDataBehavior.BLOCK.value


def test_runtime_builder_merges_authoritative_and_legacy_quality_flags(monkeypatch) -> None:
    by_timeframe = {
        "10s": [],
        "1m": _candles(30),
        "5m": _candles(30),
    }

    def fake_get_intraday_bars(**kwargs):
        return by_timeframe[str(kwargs["timeframe"])]

    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        fake_get_intraday_bars,
    )

    inputs, flags = build_runtime_pattern_inputs(
        symbol="FLAG4",
        row={
            "symbol": "FLAG4",
            "session_label": "RTH_OPEN",
            "last_price": 10.8,
            "bid": 10.79,
            "ask": 10.81,
            "spread": 0.02,
            "volume": 120_000,
            "pct_change": 8.5,
            "rvol": 6.0,
            "float_millions": 8.0,
            "prior_close": 9.9,
            "data_quality_flags": ["LEGACY_RUNTIME_FLAG", "LEGACY_RUNTIME_FLAG"],
        },
        snapshot=MarketSnapshot(
            symbol="FLAG4",
            bid=10.79,
            ask=10.81,
            last=10.8,
            volume=120_000,
            asof_utc=datetime.now(timezone.utc),
        ),
        session_label="RTH_OPEN",
        session_phase="RTH_OPEN",
    )

    assert inputs is not None
    assert "PATTERN_INPUT_BLOCK_MICRO_PULLBACK" in inputs.data_quality_flags
    assert "LEGACY_RUNTIME_FLAG" in inputs.data_quality_flags
    assert flags == ["LEGACY_RUNTIME_FLAG"]
    assert len(inputs.data_quality_flags) == len(set(inputs.data_quality_flags))


def test_opening_session_requires_10s_refinement_when_missing() -> None:
    inputs = build_authoritative_pattern_inputs(
        symbol="OPENX",
        session_label="RTH_OPEN",
        timeframe_candles={"1m": _candles(30), "5m": _candles(30)},
        indicators=IndicatorSet(ema9=10.5, ema20=10.4, ema200=9.9, vwap=10.3),
        levels=_levels(),
        liquidity_context=_liquidity(),
    )

    assert inputs.execution_refinement_timeframe == "10s"
    assert inputs.timeframe_provenance["10s"] == IndicatorProvenance.MISSING.value
    assert inputs.missing_data_actions["timeframe:10s"] == MissingDataBehavior.BLOCK.value
    assert inputs.setup_quality["MICRO_PULLBACK"]["action"] == MissingDataBehavior.BLOCK.value


def test_midday_and_late_sessions_do_not_blindly_require_10s() -> None:
    for session in ("RTH_MID", "RTH_LATE"):
        inputs = build_authoritative_pattern_inputs(
            symbol=f"{session}X",
            session_label=session,
            timeframe_candles={"1m": _candles(30), "5m": _candles(30)},
            indicators=IndicatorSet(ema9=10.5, ema20=10.4, ema200=9.9, vwap=10.3),
            levels=_levels(),
            liquidity_context=_liquidity(),
        )

        assert inputs.execution_refinement_timeframe == "1m"
        assert inputs.timeframe_provenance["10s"] == IndicatorProvenance.MISSING.value
        assert inputs.setup_quality["FIRST_PULLBACK"]["action"] in {MissingDataBehavior.IGNORE.value, MissingDataBehavior.WARN.value}
        assert inputs.missing_data_actions.get("timeframe:10s") != MissingDataBehavior.BLOCK.value


def test_missing_macd_degrades_only_setup_families_that_require_it() -> None:
    inputs = build_authoritative_pattern_inputs(
        symbol="MACDX",
        session_label="RTH_MID",
        timeframe_candles={"1m": _candles(12), "5m": _candles(12)},
        indicators=IndicatorSet(ema9=10.5, ema20=10.4, ema200=9.9, vwap=10.3),
        levels=_levels(),
        liquidity_context=_liquidity(),
    )

    assert inputs.indicator_provenance["macd_line"] == IndicatorProvenance.MISSING.value
    assert inputs.setup_quality["ABCD_CONTINUATION"]["action"] == MissingDataBehavior.DEGRADE.value
    assert inputs.setup_quality["MICRO_PULLBACK"]["indicator_provenance"]["macd_line"] == IndicatorProvenance.NOT_REQUIRED_FOR_SETUP.value


def test_missing_ema200_has_explicit_provenance_without_global_block() -> None:
    inputs = build_authoritative_pattern_inputs(
        symbol="EMA200X",
        session_label="RTH_MID",
        timeframe_candles={"1m": _candles(30), "5m": _candles(30)},
        levels=_levels(),
        liquidity_context=_liquidity(),
    )

    assert inputs.indicator_provenance["ema200"] == IndicatorProvenance.MISSING.value
    assert inputs.missing_data_actions["ema200"] == MissingDataBehavior.WARN.value
    assert inputs.setup_quality["HOD_BREAK"]["action"] in {MissingDataBehavior.IGNORE.value, MissingDataBehavior.WARN.value}


def test_missing_timeframe_actions_are_explicit_block_degrade_and_warn() -> None:
    inputs = build_authoritative_pattern_inputs(
        symbol="MISSX",
        session_label="RTH_OPEN",
        timeframe_candles={"1m": _candles(30)},
        indicators=IndicatorSet(ema9=10.5, ema20=10.4, ema200=9.9, vwap=10.3),
        levels=_levels(),
        liquidity_context=_liquidity(),
    )

    assert inputs.setup_quality["MICRO_PULLBACK"]["action"] == MissingDataBehavior.BLOCK.value
    assert inputs.setup_quality["FIRST_PULLBACK"]["action"] == MissingDataBehavior.DEGRADE.value
    assert any(
        finding["behavior"] == MissingDataBehavior.WARN.value
        for finding in inputs.setup_quality["PMH_BREAK"]["missing"]
        if finding["item"] == "timeframe:10s"
    )


def test_stale_timeframe_is_explicit_in_freshness_provenance() -> None:
    now = datetime(2026, 6, 13, 14, 0, tzinfo=timezone.utc)
    stale_start = now - timedelta(minutes=30)

    inputs = build_authoritative_pattern_inputs(
        symbol="STALEX",
        session_label="RTH_OPEN",
        timeframe_candles={"10s": _candles(5, timestamp_start=stale_start), "1m": _candles(30), "5m": _candles(30)},
        indicators=IndicatorSet(ema9=10.5, ema20=10.4, ema200=9.9, vwap=10.3),
        levels=_levels(),
        liquidity_context=_liquidity(),
        now=now,
    )

    assert inputs.timeframe_provenance["10s"] == IndicatorProvenance.STALE.value
    assert inputs.missing_data_actions["timeframe:10s"] == MissingDataBehavior.BLOCK.value
