from src.scanner.scanner_runner import GateThresholds, _resolve_pct_change_min_for_session
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_trace import build_runtime_pattern_inputs


def _thresholds() -> GateThresholds:
    return GateThresholds(
        min_price=1.0,
        max_price=100.0,
        min_pct_change=7.0,
        max_pct_change=None,
        watchlist_rvol_min=1.0,
        focus_rvol_min=1.0,
        focus_volume_min=100_000,
        focus_volume_min_early_rth=100_000,
        focus_volume_min_early_rth_ratio=0.25,
        min_volume=100_000,
        min_premarket_volume=50_000,
        max_float=100_000_000,
        spread_max_pct=0.05,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=False,
        allow_unknown_float=True,
    )


def _candles(count: int = 20) -> list[Candle]:
    return [
        Candle(open=4 + idx * 0.01, high=4.2 + idx * 0.01, low=3.9 + idx * 0.01, close=4.1 + idx * 0.01, volume=1000 + idx)
        for idx in range(count)
    ]


def test_ross_gate_preserves_ah_session_in_log_and_threshold(capsys) -> None:
    pct_min = _resolve_pct_change_min_for_session("AH", _thresholds())
    out = capsys.readouterr().out
    assert pct_min == 5.0
    assert "[ROSS][GATE] session=AH pct_change_min=5" in out


def test_ross_gate_normalizes_power_hour_to_rth_late(capsys) -> None:
    pct_min = _resolve_pct_change_min_for_session("POWER_HOUR", _thresholds())
    out = capsys.readouterr().out
    assert pct_min == 5.0
    assert "[ROSS][GATE] session=RTH_LATE pct_change_min=5" in out


def test_ross_gate_preserves_pre_threshold(capsys) -> None:
    pct_min = _resolve_pct_change_min_for_session("PRE", _thresholds())
    out = capsys.readouterr().out
    assert pct_min == 7.0
    assert "[ROSS][GATE]" not in out


def test_missing_session_raises_explicit_error(capsys) -> None:
    try:
        _resolve_pct_change_min_for_session("", _thresholds())
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert str(exc) == "missing_canonical_session"
    out = capsys.readouterr().out
    assert "[ROSS][SESSION_ERROR] missing_canonical_session" in out


def test_pattern_inputs_normalize_power_hour_to_rth_late(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: _candles(20),
    )
    row = {"symbol": "TMDE", "pct_change": 4.0, "volume": 10_000, "last_price": 4.2}
    snapshot = type("Snapshot", (), {"last": 4.2, "bid": 4.19, "ask": 4.21, "volume": 10_000})()
    inputs, _flags = build_runtime_pattern_inputs(
        symbol="TMDE",
        row=row,
        snapshot=snapshot,
        session_label="POWER_HOUR",
        session_phase="POWER_HOUR",
    )
    assert inputs is not None
    assert inputs.news_context["session_label"] == "RTH_LATE"
