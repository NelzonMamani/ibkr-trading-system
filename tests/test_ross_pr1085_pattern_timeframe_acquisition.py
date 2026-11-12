from __future__ import annotations

from src.ibkr.market_data_client import HistoricalDataResult

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.adapters.data import historical_data_provider
from src.adapters.data.historical_data_provider import get_intraday_bars as _canonical_get_intraday_bars
from src.adapters.data.historical_bar_timeframes import (
    normalize_intraday_timeframe,
    resolve_intraday_timeframe_request,
)
from src.ibkr.market_data_client import MarketDataClient
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_trace import build_runtime_pattern_inputs
from src.strategies.ross_momentum.policy import IndicatorProvenance, MissingDataBehavior


class _Manager:
    def __init__(self, client) -> None:
        self._client = client

    def get_client(self):
        return self._client


class _HistoricalProviderClient:
    def __init__(self, bars) -> None:
        self.bars = bars
        self.calls: list[dict[str, object]] = []

    def resolve_contract(self, symbol: str):
        return SimpleNamespace(contract=SimpleNamespace(symbol=symbol, conId=123, primaryExchange="NASDAQ"))

    def reqHistoricalData(self, contract, *, endDateTime, durationStr, barSizeSetting, whatToShow, useRTH, formatDate):
        self.calls.append(
            {
                "symbol": contract.symbol,
                "endDateTime": endDateTime,
                "durationStr": durationStr,
                "barSizeSetting": barSizeSetting,
                "whatToShow": whatToShow,
                "useRTH": useRTH,
                "formatDate": formatDate,
            }
        )
        return HistoricalDataResult("COMPLETE_BARS" if self.bars else "COMPLETE_EMPTY",tuple(self.bars),True)


class _HistoryIB:
    def __init__(self, bars) -> None:
        self.bars = bars
        self.calls: list[dict[str, object]] = []

    def isConnected(self):
        return True

    def reqHistoricalData(self, contract, *, endDateTime, durationStr, barSizeSetting, whatToShow, useRTH, formatDate):
        self.calls.append(
            {
                "symbol": contract.symbol,
                "endDateTime": endDateTime,
                "durationStr": durationStr,
                "barSizeSetting": barSizeSetting,
                "whatToShow": whatToShow,
                "useRTH": useRTH,
                "formatDate": formatDate,
            }
        )
        return HistoricalDataResult("COMPLETE_BARS" if self.bars else "COMPLETE_EMPTY",tuple(self.bars),True)


@pytest.fixture(autouse=True)
def _restore_canonical_historical_provider_function():
    historical_data_provider.get_intraday_bars = _canonical_get_intraday_bars
    yield
    historical_data_provider.get_intraday_bars = _canonical_get_intraday_bars


@pytest.fixture
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _raw_bars(count: int, *, timestamp_start: datetime | None = None, step_seconds: int = 60):
    start = timestamp_start or datetime(2026, 8, 28, 13, 30, tzinfo=timezone.utc)
    return [
        SimpleNamespace(
            open=10.0 + idx * 0.01,
            high=10.05 + idx * 0.01,
            low=9.95 + idx * 0.01,
            close=10.02 + idx * 0.01,
            volume=1000 + idx,
            date=start + timedelta(seconds=step_seconds * idx),
        )
        for idx in range(count)
    ]


def _candles(count: int, *, latest: datetime, step_seconds: int, start_price: float = 10.0) -> list[Candle]:
    first = latest - timedelta(seconds=step_seconds * (count - 1))
    return [
        Candle(
            open=start_price + idx * 0.01,
            high=start_price + idx * 0.01 + 0.05,
            low=start_price + idx * 0.01 - 0.04,
            close=start_price + idx * 0.01 + 0.02,
            volume=10_000 + idx,
            timestamp=first + timedelta(seconds=step_seconds * idx),
        )
        for idx in range(count)
    ]


def _row(session: str = "RTH_MID") -> dict[str, object]:
    return {
        "symbol": "AREN",
        "session_label": session,
        "last_price": 10.8,
        "bid": 10.79,
        "ask": 10.81,
        "spread": 0.02,
        "volume": 120_000,
        "pct_change": 28.72,
        "rvol": 6.0,
        "float_millions": 8.0,
        "prior_close": 9.9,
    }


@pytest.mark.parametrize(
    ("logical", "requested", "expected_bar_size", "expected_duration"),
    [
        ("10s", 120, "10 secs", 2400),
        ("1m", 50, "1 min", 6000),
        ("5m", 50, "5 mins", 30000),
    ],
)
def test_pr1085_canonical_intraday_timeframe_mapping(logical, requested, expected_bar_size, expected_duration) -> None:
    request = resolve_intraday_timeframe_request(timeframe=logical, requested_bars=requested)

    assert request.logical_timeframe == logical
    assert request.bar_size_setting == expected_bar_size
    assert request.requested_bars == requested
    assert request.duration_seconds == expected_duration
    assert request.duration_seconds >= requested * request.bar_seconds


def test_pr1085_timeframe_aliases_normalize_without_masquerading() -> None:
    assert normalize_intraday_timeframe("10 sec") == "10s"
    assert normalize_intraday_timeframe("1 min") == "1m"
    assert normalize_intraday_timeframe("5 mins") == "5m"
    assert resolve_intraday_timeframe_request(timeframe="5m", requested_bars=50).bar_size_setting != "1 min"
    assert resolve_intraday_timeframe_request(timeframe="10s", requested_bars=120).bar_size_setting != "1 min"


def test_pr1085_unsupported_timeframe_still_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        resolve_intraday_timeframe_request(timeframe="2m", requested_bars=50)


@pytest.mark.parametrize(
    ("logical", "limit", "expected_bar_size", "expected_duration"),
    [
        ("10s", 120, "10 secs", "2400 S"),
        ("1m", 50, "1 min", "6000 S"),
        ("5m", 50, "5 mins", "30000 S"),
    ],
)
def test_pr1085_historical_provider_accepts_ross_timeframes_and_issues_ibkr_request(
    monkeypatch,
    logical,
    limit,
    expected_bar_size,
    expected_duration,
) -> None:
    client = _HistoricalProviderClient(_raw_bars(limit + 5))
    monkeypatch.setattr(
        historical_data_provider,
        "get_shared_ibkr_connection_manager",
        lambda readonly_enabled=True: _Manager(client),
    )

    candles = historical_data_provider.get_intraday_bars(symbol="AREN", timeframe=logical, limit=limit)

    assert len(candles) == limit
    assert candles[0].open > 10.0
    assert candles[-1].timestamp is not None
    assert client.calls == [
        {
            "symbol": "AREN",
            "endDateTime": "",
            "durationStr": expected_duration,
            "barSizeSetting": expected_bar_size,
            "whatToShow": "TRADES",
            "useRTH": False,
            "formatDate": 2,
        }
    ]


@pytest.mark.parametrize(
    ("logical", "limit", "expected_bar_size", "expected_duration"),
    [
        ("10s", 120, "10 secs", "2400 S"),
        ("1m", 50, "1 min", "6000 S"),
        ("5m", 50, "5 mins", "30000 S"),
    ],
)
def test_pr1085_market_data_client_intraday_history_maps_logical_timeframes(
    logical,
    limit,
    expected_bar_size,
    expected_duration,
) -> None:
    ib = _HistoryIB(_raw_bars(limit + 7))
    client = MarketDataClient(snapshot_timeout_seconds=1, connection_manager=_Manager(ib))
    contract = SimpleNamespace(symbol="AREN", conId=123, primaryExchange="NASDAQ")

    bars = client.intraday_bars_from_history(contract, timeframe=logical, lookback_bars=limit, use_rth=False)

    assert len(bars) == limit
    assert ib.calls == [
        {
            "symbol": "AREN",
            "endDateTime": "",
            "durationStr": expected_duration,
            "barSizeSetting": expected_bar_size,
            "whatToShow": "TRADES",
            "useRTH": False,
            "formatDate": 1,
        }
    ]


@pytest.mark.parametrize(("stamp", "expected_minute_limit"), [
    ("2026-10-20T13:40:30+00:00", 50),
    ("2026-10-20T16:35:30+00:00", 187),
])
def test_pr1085_runtime_pattern_bundle_marks_all_real_timeframes_present(
    monkeypatch, stamp, expected_minute_limit,
) -> None:
    # Source freshness and acquisition span share one original observation.
    # This test must cover both windows regardless of the CI machine's clock.
    from src.strategies.ross_momentum.patterns import pattern_trace
    now_utc = datetime.fromisoformat(stamp)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now_utc
    monkeypatch.setattr(pattern_trace, "datetime", Clock)
    calls: list[tuple[str, int]] = []
    by_timeframe = {
        "10s": _candles(120, latest=now_utc, step_seconds=10, start_price=10.0),
        "1m": _candles(50, latest=now_utc, step_seconds=60, start_price=10.2),
        "5m": _candles(50, latest=now_utc, step_seconds=300, start_price=10.4),
    }

    def fake_get_intraday_bars(**kwargs):
        calls.append((str(kwargs["timeframe"]), int(kwargs["limit"])))
        return by_timeframe[str(kwargs["timeframe"])]

    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        fake_get_intraday_bars,
    )

    inputs, flags = build_runtime_pattern_inputs(
        symbol="AREN",
        row=_row("RTH_OPEN"),
        snapshot=None,
        session_label="RTH_OPEN",
        session_phase="RTH_OPEN",
    )

    assert inputs is not None
    assert flags == []
    assert calls == [("10s", 120), ("1m", expected_minute_limit), ("5m", 50)]
    assert inputs.observed_at_utc == now_utc
    assert len(inputs.candles) == len(inputs.timeframe_candles["1m"]) == 50
    if expected_minute_limit > 50:
        # A partial external response is fresh data, not complete-day HOD authority.
        assert inputs.levels.established_rth_hod is None
    assert set(inputs.timeframe_candles) == {"10s", "1m", "5m"}
    assert inputs.timeframe_provenance == {
        "10s": IndicatorProvenance.PRESENT.value,
        "1m": IndicatorProvenance.PRESENT.value,
        "5m": IndicatorProvenance.PRESENT.value,
    }


def test_pr1085_rth_mid_does_not_block_merely_because_10s_is_missing(monkeypatch, now_utc) -> None:
    by_timeframe = {
        "10s": [],
        "1m": _candles(50, latest=now_utc, step_seconds=60, start_price=10.2),
        "5m": _candles(50, latest=now_utc, step_seconds=300, start_price=10.4),
    }

    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: by_timeframe[str(kwargs["timeframe"])],
    )

    inputs, _flags = build_runtime_pattern_inputs(
        symbol="AREN",
        row=_row("RTH_MID"),
        snapshot=None,
        session_label="RTH_MID",
        session_phase="RTH_MID",
    )

    assert inputs is not None
    assert inputs.execution_refinement_timeframe == "1m"
    assert inputs.context_timeframe == "5m"
    assert inputs.timeframe_provenance["10s"] == IndicatorProvenance.MISSING.value
    assert inputs.timeframe_provenance["1m"] == IndicatorProvenance.PRESENT.value
    assert inputs.timeframe_provenance["5m"] == IndicatorProvenance.PRESENT.value
    assert inputs.missing_data_actions.get("timeframe:10s") != MissingDataBehavior.BLOCK.value
    assert inputs.missing_data_actions.get("timeframe:5m") != MissingDataBehavior.BLOCK.value


def test_pr1085_required_rth_mid_5m_missing_remains_blocked(monkeypatch, now_utc) -> None:
    by_timeframe = {
        "10s": [],
        "1m": _candles(50, latest=now_utc, step_seconds=60, start_price=10.2),
        "5m": [],
    }

    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: by_timeframe[str(kwargs["timeframe"])],
    )

    inputs, _flags = build_runtime_pattern_inputs(
        symbol="AREN",
        row=_row("RTH_MID"),
        snapshot=None,
        session_label="RTH_MID",
        session_phase="RTH_MID",
    )

    assert inputs is not None
    assert inputs.timeframe_provenance["1m"] == IndicatorProvenance.PRESENT.value
    assert inputs.timeframe_provenance["5m"] == IndicatorProvenance.MISSING.value
    assert inputs.missing_data_actions["timeframe:5m"] == MissingDataBehavior.BLOCK.value
    assert "PATTERN_INPUT_BLOCK_ORB_GAP_GO" in inputs.data_quality_flags


def test_pr1085_stale_required_rth_mid_5m_remains_blocked(monkeypatch, now_utc) -> None:
    by_timeframe = {
        "10s": [],
        "1m": _candles(50, latest=now_utc, step_seconds=60, start_price=10.2),
        "5m": _candles(50, latest=now_utc - timedelta(minutes=45), step_seconds=300, start_price=10.4),
    }

    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars",
        lambda **kwargs: by_timeframe[str(kwargs["timeframe"])],
    )

    inputs, _flags = build_runtime_pattern_inputs(
        symbol="AREN",
        row=_row("RTH_MID"),
        snapshot=None,
        session_label="RTH_MID",
        session_phase="RTH_MID",
    )

    assert inputs is not None
    assert inputs.timeframe_provenance["5m"] == IndicatorProvenance.STALE.value
    assert inputs.missing_data_actions["timeframe:5m"] == MissingDataBehavior.BLOCK.value
    assert "PATTERN_INPUT_BLOCK_ORB_GAP_GO" in inputs.data_quality_flags


@pytest.mark.parametrize('outcome',['epoch','empty','partial'])
def test_native_intraday_adapter_retains_end_identity_and_original_utc_epoch(monkeypatch,outcome):
    stamp=datetime(2026,11,9,9,0,tzinfo=timezone.utc)
    bar=SimpleNamespace(open=10.,high=10.3,low=9.9,close=10.2,volume=100,date=str(int(stamp.timestamp())))
    client=_HistoricalProviderClient([])
    def request(contract,**kw):
        assert kw['formatDate']==2
        return HistoricalDataResult('COMPLETE_EMPTY' if outcome=='empty' else 'COMPLETE_BARS' if outcome=='epoch' else 'TIMEOUT',
            () if outcome=='empty' else (bar,),outcome!='partial')
    client.reqHistoricalData=request
    monkeypatch.setattr(historical_data_provider,'get_shared_ibkr_connection_manager',lambda **kw:_Manager(client))
    result=historical_data_provider.get_intraday_bars(symbol='AREN')
    assert result.completed is (outcome!='partial')
    assert result.contract_identity.symbol=='AREN' and result.contract_identity.con_id==123
    if outcome=='epoch':assert result[0].timestamp==stamp and result[0].timestamp.tzinfo is timezone.utc
    else:assert not result


def test_premarket_bootstrap_does_not_acquire_a_weekend_reference(monkeypatch,tmp_path):
    from src.strategies.ross_momentum.patterns import pattern_trace
    from src.market_data.reference_resolver import PersistentReferenceCache
    now=datetime(2026,11,14,17,35,30,tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return now
    monkeypatch.setattr(pattern_trace,'datetime',Clock) # Existing local observation seam, no shared time patch.
    monkeypatch.setattr(pattern_trace,'PersistentReferenceCache',lambda:PersistentReferenceCache(tmp_path/'ref.json'))
    calls=[]
    streams={'10s':_candles(120,latest=now,step_seconds=10,start_price=10.),
        '1m':_candles(50,latest=now,step_seconds=60,start_price=10.2),
        '5m':_candles(50,latest=now,step_seconds=300,start_price=10.4)}
    def external(**kw):
        calls.append(kw)
        return streams[kw['timeframe']]
    monkeypatch.setattr(pattern_trace,'get_intraday_bars',external)
    row=dict(_row('RTH_MID'),con_id=123)
    inputs,_=pattern_trace.build_runtime_pattern_inputs(symbol='AREN',row=row,snapshot=None,
        session_label='RTH_MID',session_phase='RTH_MID')
    assert inputs.levels.premarket_reference['status']=='MISSING'
    assert inputs.levels.premarket_reference['reason']=='PRE_REFERENCE_OUTSIDE_TRADING_DATE'
    assert [kw['timeframe'] for kw in calls]==['10s','1m','5m']
    assert not (tmp_path/'ref.json').exists()


@pytest.mark.parametrize(('label', 'expected', 'observed'), [
    ('OPENING_0_30', 'REGULAR', datetime(2026, 10, 20, 13, 35, 30, tzinfo=timezone.utc)),
    ('MORNING', 'REGULAR', datetime(2026, 10, 20, 14, 35, 30, tzinfo=timezone.utc)),
    ('RTH_OPEN', 'REGULAR', datetime(2026, 10, 20, 13, 35, 30, tzinfo=timezone.utc)),
    ('PRE', 'PRE', datetime(2026, 10, 20, 13, 25, 30, tzinfo=timezone.utc)),
    ('UNKNOWN', 'PRE', datetime(2026, 10, 20, 13, 35, 30, tzinfo=timezone.utc)),
])
def test_runtime_phase_preserves_coarse_session_and_own_opening_permission(
        monkeypatch, tmp_path, label, expected, observed):
    from ibapi.client import EClient
    from src.core_engine.state import SessionState
    from src.strategies.common.patterns.pattern_opening_drive import detect_opening_drive
    from src.strategies.ross_momentum.patterns import pattern_trace
    from src.strategies.ross_momentum.policy.pattern_input_policy import PatternInputPolicy
    from src.utils.time_utils import market_session_phase, resolve_session_state

    def forbidden(*args, **kwargs):
        raise AssertionError('Broker/SDK activity forbidden in raw-history component control')
    for method in ('connect', 'placeOrder', 'cancelOrder', 'reqGlobalCancel'):
        monkeypatch.setattr(EClient, method, forbidden)
    monkeypatch.chdir(tmp_path)
    policy = PatternInputPolicy.from_policy_v2()
    assert policy.plan_for_session(label) == policy.plan_for_session('RTH_OPEN')
    if label in {'OPENING_0_30', 'MORNING'}:
        assert market_session_phase(observed) == label
        assert resolve_session_state(observed) is SessionState.REG

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return observed.astimezone(tz) if tz else observed
    monkeypatch.setattr(pattern_trace, 'datetime', Clock)
    streams = {tf: _candles(50, latest=observed-timedelta(seconds=seconds), step_seconds=seconds)
        for tf, seconds in (('10s', 10), ('1m', 60), ('5m', 300))}
    original_clocks = {tf: [c.timestamp for c in bars] for tf, bars in streams.items()}
    calls = []
    def supplied_history(**kwargs):
        calls.append(kwargs)
        return streams[kwargs['timeframe']][-kwargs.get('limit', 50):]
    monkeypatch.setattr(pattern_trace, 'get_intraday_bars', supplied_history)
    # Only raw observations enter the real builder; it derives quality, levels,
    # percentage change, RVOL, session context and the existing timeframe plan.
    row = dict(symbol='AREN', last_price=10.8, bid=10.79, ask=10.81, volume=2_000_000,
        previous_close=9.9, average_daily_volume_20d=200_000, float_shares=8_000_000)
    inputs, _ = build_runtime_pattern_inputs(symbol='AREN', row=row, snapshot=None,
        session_label=label, session_phase=label)
    assert inputs is not None and inputs.session_context.value == expected
    assert inputs.session_label == inputs.session_phase == label
    assert (inputs.primary_timeframe, inputs.execution_refinement_timeframe, inputs.context_timeframe) == ('1m', '10s', '5m')
    assert [call['timeframe'] for call in calls] == ['10s', '1m', '5m']
    assert {tf: [c.timestamp for c in bars] for tf, bars in streams.items()} == original_clocks
    if label == 'MORNING':
        # A regular session does not extend this family's own opening window.
        result = detect_opening_drive(inputs)
        assert not result.detected and result.rejection_reason == 'invalid_phase'
        assert result.target_suggestion is None
