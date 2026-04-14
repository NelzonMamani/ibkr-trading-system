from __future__ import annotations

from types import SimpleNamespace

from src.core.orchestrator import CoreOrchestrator


class _ClientStub:
    def __init__(self, bars):
        self._bars = bars
        self.daily_called = False

    def intraday_bars_from_history(self, symbol, *, timeframe: str, lookback_bars: int, use_rth: bool):
        assert symbol == "MNTS"
        assert timeframe == "1m"
        assert lookback_bars >= 2
        assert use_rth is False
        return self._bars

    def daily_bars_from_history(self, *args, **kwargs):
        self.daily_called = True
        raise AssertionError("daily_bars_from_history should not be used for trade management")



def _mk_orchestrator(*, bars, entry_price: float = 10.0):
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    orchestrator.connection_manager = SimpleNamespace(optional_client=_ClientStub(bars))
    orchestrator.trade_management_engine = SimpleNamespace(
        snapshot_positions=lambda: {
            "MNTS": SimpleNamespace(entry_price=entry_price),
        }
    )
    return orchestrator



def test_trade_management_market_state_uses_intraday_bars_and_derives_fields(capsys):
    bars = [
        SimpleNamespace(open=9.8, high=10.0, low=9.7, close=9.9, volume=1000),
        SimpleNamespace(open=9.9, high=10.2, low=9.85, close=10.1, volume=1500),
        SimpleNamespace(open=10.1, high=10.3, low=10.0, close=10.2, volume=1700),
        SimpleNamespace(open=10.2, high=10.35, low=10.05, close=10.15, volume=1300),
        SimpleNamespace(open=10.15, high=10.4, low=10.1, close=10.3, volume=1600),
    ]
    orchestrator = _mk_orchestrator(bars=bars, entry_price=10.0)

    state = orchestrator._build_trade_management_market_state()

    assert "MNTS" in state
    market_state = state["MNTS"]
    assert market_state["open"] == 10.15
    assert market_state["close"] == 10.3
    assert market_state["current_volume"] == 1600.0
    # Last 3 lows are: 10.0, 10.05, 10.1
    assert market_state["pullback_low"] == 10.0
    assert market_state["no_progress"] is False

    output = capsys.readouterr().out
    assert "[DATA][INTRADAY_CANDLE_SOURCE] symbol=MNTS" in output
    assert "timeframe=1m" in output
    assert "source=market_data_client.intraday_bars_from_history" in output
    assert "[DATA][MARKET_STATE_READY] symbol=MNTS timeframe=1m" in output
    assert "[ROSS][EXIT_INPUT_PROXY] symbol=MNTS" in output



def test_trade_management_market_state_sets_dynamic_no_progress_when_price_not_advancing():
    bars = [
        SimpleNamespace(open=9.98, high=10.01, low=9.95, close=9.99, volume=1000),
        SimpleNamespace(open=9.99, high=10.0, low=9.96, close=9.98, volume=1100),
        SimpleNamespace(open=9.98, high=10.0, low=9.97, close=9.99, volume=1200),
    ]
    orchestrator = _mk_orchestrator(bars=bars, entry_price=10.0)

    state = orchestrator._build_trade_management_market_state()

    assert state["MNTS"]["no_progress"] is True



def test_trade_management_market_state_logs_and_skips_when_intraday_missing(capsys):
    orchestrator = _mk_orchestrator(bars=[])

    state = orchestrator._build_trade_management_market_state()

    assert state == {}
    output = capsys.readouterr().out
    assert "[DATA][MISSING_INTRADAY_CANDLES] symbol=MNTS" in output
    assert "[ROSS][EXIT_INTELLIGENCE][SKIP] symbol=MNTS reason=MISSING_INTRADAY_CANDLES" in output
