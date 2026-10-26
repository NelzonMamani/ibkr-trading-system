"""Virtual-clock multi-symbol scheduling; real gates, no transport or sleeps."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from src.core.acquisition import AcquisitionCancelled, acquisition_scope, bounded_timeout, checkpoint
from src.scanner import scanner_runner as scanner
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy


@pytest.mark.parametrize('outside_age', [30, 14])
@pytest.mark.parametrize('tail', ['timeout', 'stale'])
def test_slow_tail_cannot_spend_fresh_leaders_selection_reserve(monkeypatch, tail, outside_age, capsys):
    clock = [0.0]
    origin = datetime(2026, 10, 20, 14, 34, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return origin + timedelta(seconds=clock[0])
    monkeypatch.setattr(scanner, 'datetime', Clock)
    monkeypatch.setattr(scanner.time, 'monotonic', lambda: clock[0])
    policy = RossMomentumPolicy().stock_selection
    thresholds = scanner._gate_thresholds(policy, scanner._resolve_runtime_thresholds(policy))
    def row(symbol, age=30):
        return dict(symbol=symbol, con_id=100 + symbols.index(symbol), session='RTH_OPEN',
                    quote_timestamp_utc=(Clock.now()-timedelta(seconds=age)).isoformat(),
                    quote_timestamp_source='LAST_TRADE', data_quality_flags=[], eligibility_reason_codes=[],
                    last_price=6., bid=5.99, ask=6.01, spread_pct=.0034, pct_change=15.,
                    float_shares=8_000_000, rvol=10., rvol_discovery=10., rvol_phase=10.,
                    volume=2_000_000, premarket_volume=2_000_000, dollar_volume=12_000_000,
                    catalyst_present=True, catalyst_status='CONFIRMED', scanner_score=1.)
    symbols = ['WORX', 'NCPL', 'AIXI', 'HUIZ', 'SLOW', 'TAIL1', 'TAIL2', 'TAIL3', 'TAIL4', 'OUTSIDE_K']
    rows = [row(s) for s in symbols]
    rows[-1].update(row(symbols[-1], outside_age))
    calls, stamps = [], {}
    def refresh(symbol):
        calls.append(symbol)
        duration = 1. if symbol in symbols[:4] else (20. if tail == 'timeout' else 2.)
        clock[0] += bounded_timeout(duration)
        checkpoint()  # Same absolute deadline/cancellation boundary as real transport.
        stamp = (Clock.now()-timedelta(seconds=0 if symbol in symbols[:4] else 100)).isoformat()
        stamps[symbol] = stamp
        return NS(symbol=symbol, timestamp_utc=stamp, timestamp_source='LAST_TRADE')
    def rebuild(provider, symbol, session, **kwargs):
        return dict(row(symbol, 0), quote_timestamp_utc=kwargs['quote_override'].timestamp_utc)
    monkeypatch.setattr(scanner, '_rank_candidates', lambda contexts: list(contexts))
    monkeypatch.setattr(scanner, '_build_symbol_context', rebuild)
    ledger = {}
    with acquisition_scope(lambda: False):
        survivors = scanner._refresh_provisional_shortlist(rows, NS(refresh_quote=refresh), 'RTH_OPEN', {},
                                                         9, thresholds, ledger, deadline_s=100.)
    assert [r['symbol'] for r in survivors] == symbols[:4]
    assert calls[:4] == symbols[:4] and 'OUTSIDE_K' not in calls
    assert len(calls) <= 9 and len(set(calls)) == len(calls)  # No refresh retry rounds.
    assert clock[0] == pytest.approx(11.)  # First leader timestamp1 + age15 - reserve5.
    for r in survivors:
        assert r['quote_timestamp_utc'] == stamps[r['symbol']]
        assert scanner._evaluate_watchlist_gates(r, thresholds) is None
        assert scanner._evaluate_focus_gates(r, thresholds) is None
    assert set(ledger.values()) == {'DROP_STALE_MARKET_DATA'}
    output = capsys.readouterr().out
    assert 'reason=LEADER_FRESHNESS_RESERVE' in output
    assert '[SCANNER][SHORTLIST_ASSESSMENT] symbol=WORX' in output and 'reason=PASS' in output
    # Actual later delay still rejects the retained original broker timestamps.
    clock[0] = 25.
    assert all(scanner._evaluate_focus_gates(r, thresholds) == 'DROP_STALE_MARKET_DATA' for r in survivors)


def test_multi_candidate_refresh_stop_preempts_deadline(monkeypatch):
    rows = [dict(quote_timestamp_source='LAST_TRADE', symbol=s, quote_timestamp_utc='2020-01-01T00:00:00+00:00', data_quality_flags=[])
            for s in ['FIRST', 'SECOND', 'THIRD']]
    monkeypatch.setattr(scanner, '_rank_candidates', lambda contexts: contexts)
    monkeypatch.setattr(scanner, '_shortlist_selection_deadline', lambda *args: None)
    stopped = False
    calls = []
    def refresh(symbol):
        nonlocal stopped
        calls.append(symbol)
        stopped = True
        return NS(symbol=symbol)
    with pytest.raises(AcquisitionCancelled), acquisition_scope(lambda: stopped):
        scanner._refresh_provisional_shortlist(rows, NS(refresh_quote=refresh), 'RTH', {}, 3, None, {})
    assert calls == ['FIRST']
