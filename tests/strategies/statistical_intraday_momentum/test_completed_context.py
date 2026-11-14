"""Real historical dispatch/callback/provider/context owners; synthetic SDK only."""
import asyncio
from copy import deepcopy
from dataclasses import asdict, replace, FrozenInstanceError
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace as NS

import pytest
from ibapi.client import EClient

from test_history_completion_ownership import owner, chain, contract, prohibit_acquisition_and_mutation
from test_next_session_catalyst import receipt
from src.config import config_resolver as cfg
from src.ibkr import market_data_client as md_module
from src.adapters.brokers.ibkr import ibkr_client as native
from src.adapters.data import historical_data_provider as provider_module
from src.market_data import reference_resolver as ref_module
from src.market_data.candidate_identity import CandidateIdentity
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.statistical_intraday_momentum.strategy_policy import default_policy
from src.strategies.statistical_intraday_momentum.signal_engine.features import (
    CompletedContextError, build_completed_context, build_feature_vector,
)
from src.strategies.statistical_intraday_momentum.signal_engine.signal_decision import decide_completed_intent
from src.strategies.statistical_intraday_momentum.signal_engine.scoring import compute_score
from src.strategy_portfolio.contracts import AllowState, SignalIntent

UTC = timezone.utc
NOW = datetime(2026, 11, 13, 15, 5, 5, tzinfo=UTC)
OPEN = NOW.replace(hour=14, minute=30, second=0)
END = NOW.replace(second=2)


class AcquisitionClock(datetime):
    current = END - timedelta(seconds=1)

    @classmethod
    def now(cls, tz=None):
        return cls.current if tz is None else cls.current.astimezone(tz)


def activated():
    policy = default_policy()
    return replace(policy, activation=replace(policy.activation, allow=True))


@pytest.fixture
def facts(chain, monkeypatch):
    for name in ('FORCE_SESSION', 'SESSION_OVERRIDE', 'MARKET_SESSION_OVERRIDE'):
        monkeypatch.delenv(name, raising=False)
    cfg.set_config_overrides(dict(MARKET_SESSION_COVERAGE=json.dumps(receipt('2026-11-12', '2026-11-13')),
        MARKET_HOLIDAYS=set(), MARKET_HALF_DAYS=set(), SESSION_PHASE_OVERRIDE=None,
        LIVE_EXECUTION_PROBE_MODE=False))
    monkeypatch.setattr(native, 'datetime', AcquisitionClock)
    AcquisitionClock.current = END - timedelta(seconds=1)
    monkeypatch.setattr(ref_module, 'get_us_eastern_now', lambda: NOW.astimezone(ref_module.ZoneInfo('America/New_York')))
    c = chain.owner.client
    monkeypatch.setattr(c, 'resolve_contract', lambda symbol: contract())
    monkeypatch.setattr(provider_module, 'get_shared_ibkr_connection_manager', lambda **kw: NS(get_client=lambda: c))
    closes = [100.]
    for index in range(34):
        closes.append(closes[-1] * (.99 if index % 5 == 4 else 1.02))
    bars = [NS(date=str(int((OPEN + timedelta(minutes=i)).timestamp())), open=close,
        high=close + .1, low=close - .1, close=close, volume=7000 if i >= 30 else 1000)
        for i, close in enumerate(closes)]
    dispatched = []

    def send(self, req_id, con, end, duration, size, what, rth, fmt, streaming, options):
        dispatched.append((req_id, deepcopy(con), end, duration, size, what, rth, fmt, streaming, options))
        values = bars if size == '1 min' else [NS(date='20261112', close=90., volume=1_000_000)]
        for value in values:
            c.historicalData(req_id, value)
        AcquisitionClock.current = getattr(c, "_synthetic_history_end", END)
        c.historicalDataEnd(req_id, 'raw-broker-start', 'raw-broker-end')
    monkeypatch.setattr(EClient, 'reqHistoricalData', send)
    history = provider_module.get_intraday_bars(symbol='SYNTH', timeframe='1m', limit=40)
    identity = CandidateIdentity.from_contract(contract())
    reference = chain.resolver.resolve(identity=identity, provider=chain.provider,
        session_label='RTH_OPEN', current_volume=1_000_000, intraday_avg_volume_20d=None,
        current_last_price=closes[-1], rth_open_price=100., rth_close_price=None,
        ibkr_change_pct=None, persisted_pct_change=None, intraday_history_end_received=True)
    quote = MarketSnapshot(symbol='SYNTH', con_id=123, bid=closes[-1]-.01, ask=closes[-1]+.01,
        last=closes[-1], volume=1_000_000, asof_utc=END, received_at_utc=END,
        snapshot_complete=True, market_data_type_confirmed=True, returned_market_data_type='LIVE',
        market_data_type='LIVE', requested_market_data_type='LIVE', timestamp_source='LAST_TRADE', market_timestamp_utc=END,
        request_id=801, request_completed_at_utc=END.isoformat(), snapshot_completed_at_utc=END.isoformat(),
        field_received_at_utc={'last': END.isoformat()})
    yield NS(history=history, identity=identity, reference=reference, quote=quote,
             assessed_at=NOW, sent=dispatched, bars=bars, chain=chain)
    cfg.set_config_overrides(None)


def build(facts, **changes):
    return build_completed_context(**{key: changes.get(key, getattr(facts, key))
        for key in ('history', 'identity', 'quote', 'reference', 'assessed_at')})


def test_actual_wire_end_provider_context_and_native_component(facts):
    h = facts.history
    assert h.completed and h.contract_identity == facts.identity
    assert h.request_spec.bar_size_setting == '1 min' and h.request_spec.what_to_show == 'TRADES'
    assert h.request_spec.format_date == 2 and h.request_spec.timestamp_semantics == 'UTC_BAR_START'
    assert h.callback_start == 'raw-broker-start' and h.callback_end == 'raw-broker-end'
    assert h.request_dispatched_at_utc == (END-timedelta(seconds=1)).isoformat()
    assert h.completed_at_utc == END.isoformat()
    assert facts.sent[0][4:9] == ('1 min', 'TRADES', 0, 2, False)
    before = deepcopy(asdict(h)), deepcopy(asdict(facts.quote)), deepcopy(asdict(facts.reference))
    context = build(facts)
    assert len(context['bars_1m']) == 35 and len(context['bars_5m']) == 7
    assert context['bars_5m'][0]['timestamp'] == OPEN
    assert context['bars_5m'][0]['end_timestamp'] == OPEN + timedelta(minutes=5)
    assert context['bars_5m'][0]['volume'] == 5000
    assert context['bars_5m'][0]['source_timestamps'] == h.raw_bar_timestamps[:5]
    assert context['bars_1m'][0]['raw_timestamp'] == h.raw_bar_timestamps[0]
    features = build_feature_vector(context['bars_1m'], context['bars_5m'], 'open')
    score = compute_score(features, default_policy().signal)
    assert .7 <= score.score <= 1.
    assert decide_completed_intent(context, activated(), assessed_at=NOW).signal_intent == SignalIntent.ENTER_LONG
    off = decide_completed_intent(context, default_policy(), assessed_at=NOW)
    assert off.allow_state == AllowState.DISALLOW and off.signal_intent == SignalIntent.NO_TRADE
    assert before == (asdict(h), asdict(facts.quote), asdict(facts.reference))
    # Neither abstract component result supplies ATR/SF/XL/risk or a TradeIntent.
    assert 'setup_family_id' not in context and 'atr' not in context


@pytest.mark.parametrize('fault', ['unknown_spec', 'custom_size', 'midpoint', 'format1', 'streaming',
    'missing_end', 'missing_request', 'foreign', 'wrong_symbol', 'missing_identity', 'quote_foreign',
    'reference_foreign', 'reference_old', 'reference_degraded', 'naive', 'bool_price', 'nan',
    'gap', 'reordered', 'duplicate', 'prior_session', 'forming_at_completion', 'future_completion',
    'dispatch_after_end', 'stale', 'quote_future', 'quote_historical_future', 'quote_missing', 'quote_crossed'])
def test_missing_conflicting_or_unusable_sources_refuse(facts, fault):
    h, q, r = facts.history, facts.quote, facts.reference
    values = list(h.bars)
    raw_values = list(h.raw_bar_timestamps)
    if fault == 'unknown_spec': h = replace(h, request_spec=None)
    if fault == 'custom_size': h = replace(h, request_spec=replace(h.request_spec, bar_size_setting='custom'))
    if fault == 'midpoint': h = replace(h, request_spec=replace(h.request_spec, what_to_show='MIDPOINT'))
    if fault == 'format1': h = replace(h, request_spec=replace(h.request_spec, format_date=1))
    if fault == 'streaming': h = replace(h, request_spec=replace(h.request_spec, keep_up_to_date=True))
    if fault == 'missing_end': h = replace(h, end_received=False)
    if fault == 'missing_request': h = replace(h, request_id=None)
    if fault == 'foreign': h = replace(h, contract_identity=replace(h.contract_identity, con_id=456))
    if fault == 'wrong_symbol': h = replace(h, contract_identity=replace(h.contract_identity, symbol='OTHER'))
    if fault == 'missing_identity': h = replace(h, contract_identity=None)
    if fault == 'quote_foreign': q = replace(q, con_id=456)
    if fault == 'reference_foreign': r = replace(r, qualified_identity=replace(r.qualified_identity, con_id=456))
    if fault == 'reference_old': r = replace(r, reference_trading_date='2026-11-11')
    if fault == 'reference_degraded': r = replace(r, reference_degraded=True)
    if fault == 'naive': values[0] = replace(values[0], timestamp=values[0].timestamp.replace(tzinfo=None))
    if fault == 'bool_price': values[0] = replace(values[0], close=True)
    if fault == 'nan': values[0] = replace(values[0], volume=float('nan'))
    if fault == 'gap':
        del values[4]; del raw_values[4]
    if fault == 'reordered':
        values[4], values[5] = values[5], values[4]
        raw_values[4], raw_values[5] = raw_values[5], raw_values[4]
    if fault == 'duplicate':
        values.insert(4, values[4]); raw_values.insert(4, raw_values[4])
    if fault == 'prior_session':
        values[0] = replace(values[0], timestamp=values[0].timestamp-timedelta(days=1))
        raw_values[0] = str(int(values[0].timestamp.timestamp()))
    if fault == 'forming_at_completion': h = replace(h, completed_at_utc=(END-timedelta(seconds=3)).isoformat())
    if fault == 'future_completion': h = replace(h, completed_at_utc=(NOW+timedelta(seconds=1)).isoformat())
    if fault == 'dispatch_after_end': h = replace(h, request_dispatched_at_utc=(END+timedelta(seconds=1)).isoformat())
    if fault == 'stale': values = values[:-1]; raw_values = raw_values[:-1]
    if fault == 'quote_future': q = replace(q, market_timestamp_utc=NOW+timedelta(microseconds=1))
    if fault == 'quote_historical_future': q = replace(q, data_quality_flags=('MD_TIMESTAMP_FUTURE',))
    if fault == 'quote_missing': q = replace(q, bid=None)
    if fault == 'quote_crossed': q = replace(q, bid=q.ask+.01)
    if values != list(facts.history.bars): h = replace(h, bars=tuple(values), raw_bar_timestamps=tuple(raw_values))
    with pytest.raises(CompletedContextError): build(facts, history=h, quote=q, reference=r)


@pytest.mark.parametrize('target', ['raw', 'derived', 'calendar', 'clock', 'expiry', 'config'])
def test_consumer_revalidates_detached_raw_derived_and_current_authority(facts, target):
    context = build(facts)
    when = NOW
    if target == 'raw': context.source_facts['quote']['last'] += 1
    if target == 'derived': context.payload['bars_1m'][0]['close'] += 1
    if target == 'calendar':
        cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES, MARKET_SESSION_COVERAGE='{}'))
    if target == 'config':
        cfg.set_config_overrides(dict(cfg._CONFIG_OVERRIDES, IBKR_SNAPSHOT_MAX_AGE_SECONDS=999))
    if target == 'clock': when = END-timedelta(seconds=1)
    if target == 'expiry': when = OPEN+timedelta(hours=1)
    decision = decide_completed_intent(context, activated(), assessed_at=when)
    assert decision.allow_state == AllowState.DISALLOW and decision.signal_intent == SignalIntent.NO_TRADE
    assert decision.metadata['context_rejection']


def test_original_mutation_cannot_renew_detached_context_or_known_rejection(facts):
    context = build(facts)
    facts.quote.field_received_at_utc['last'] = (NOW+timedelta(days=1)).isoformat()
    assert context.source_facts['quote']['field_received_at_utc']['last'] == END.isoformat()
    assert decide_completed_intent(context, activated(), assessed_at=NOW).signal_intent == SignalIntent.ENTER_LONG
    later = NOW+timedelta(minutes=1)
    assert decide_completed_intent(context, activated(), assessed_at=later).signal_intent == SignalIntent.NO_TRADE


def test_open_aligned_incomplete_five_minute_block_is_not_aggregated(facts):
    extra = deepcopy(facts.bars[-1])
    extra.date = str(int((OPEN+timedelta(minutes=35)).timestamp()))
    facts.bars.append(extra)
    now = OPEN+timedelta(minutes=36, seconds=5)
    AcquisitionClock.current = now
    # New external request through the same real owner; no manually completed result.
    facts.chain.owner.client._synthetic_history_end = now
    h = provider_module.get_intraday_bars(symbol='SYNTH', timeframe='1m', limit=40)
    context = build(facts, history=h, quote=replace(facts.quote, market_timestamp_utc=now, asof_utc=now), assessed_at=now)
    assert len(context['bars_1m']) == 36 and len(context['bars_5m']) == 7


@pytest.mark.parametrize('kind', ['malformed_forming_extra', 'malformed_last', 'valid_forming_extra'])
def test_actual_normalizer_cannot_hide_rejected_or_forming_sdk_tail(facts, kind):
    if kind.endswith('extra'):
        value = deepcopy(facts.bars[-1])
        value.date = str(int((OPEN+timedelta(minutes=35)).timestamp()))
        if kind == 'malformed_forming_extra': value.open = 'not-a-price'
        facts.bars.append(value)
    else:
        facts.bars[-1].close = None
    h = provider_module.get_intraday_bars(symbol='SYNTH', timeframe='1m', limit=40)
    assert h.source_bar_count == len(facts.bars)
    assert len(h.raw_bar_timestamps) == len(facts.bars)
    assert h.normalization_selected_count == len(facts.bars)
    assert h.normalization_source_bars[-1]['date'] == facts.bars[-1].date
    assert h.normalization_rejected_count == (0 if kind == 'valid_forming_extra' else 1)
    with pytest.raises(CompletedContextError): build(facts, history=h)
    # Waiting does not complete a bar in the original acquisition or erase a
    # known normalization rejection. A new quote cannot renew old history.
    later = NOW+timedelta(minutes=1)
    q = replace(facts.quote, asof_utc=later, market_timestamp_utc=later)
    with pytest.raises(CompletedContextError): build(facts, history=replace(h, reused=True), quote=q, assessed_at=later)


def test_actual_limit_slice_retains_whole_source_count_and_exact_selected_mapping(facts):
    prefix=[]
    for index in range(5):
        value=deepcopy(facts.bars[0]);value.date=str(int((OPEN-timedelta(minutes=5-index)).timestamp()))
        prefix.append(value)
    facts.bars[:0]=prefix
    h=provider_module.get_intraday_bars(symbol='SYNTH',timeframe='1m',limit=35)
    assert h.source_bar_count==40 and len(h.raw_bar_timestamps)==40
    assert h.normalization_selected_count==len(h.bars)==35 and h.normalization_rejected_count==0
    assert h.normalized_raw_bar_timestamps==h.raw_bar_timestamps[-35:]
    context=build(facts,history=h)
    assert context['bars_1m'][0]['timestamp']==OPEN
    assert context.source_facts['history']['source_bar_count']==40


@pytest.mark.parametrize('age,eligible', [(0,True), (59.999999,True), (60,False)])
def test_original_completed_bar_freshness_interval_boundaries(facts,age,eligible):
    completion=OPEN+timedelta(minutes=35)
    AcquisitionClock.current=completion-timedelta(seconds=1)
    facts.chain.owner.client._synthetic_history_end=completion
    history=provider_module.get_intraday_bars(symbol='SYNTH',timeframe='1m',limit=40)
    when=completion+timedelta(seconds=age)
    quote=replace(facts.quote,asof_utc=when,market_timestamp_utc=when)
    if eligible:
        assert build(facts,history=history,quote=quote,assessed_at=when)['bars_1m'][-1]['end_timestamp']==completion
    else:
        with pytest.raises(CompletedContextError,match='HISTORY_STALE_OR_FUTURE'):
            build(facts,history=history,quote=quote,assessed_at=when)


def test_legacy_identity_projection_cannot_repair_lost_dispatch_identity(facts,monkeypatch):
    client=facts.chain.owner.client
    owned=client.reqHistoricalData
    def legacy_wrapper(*args,**kwargs):
        result=owned(*args,**kwargs)
        return replace(result,contract_identity=None,dispatched_contract_identity=None)
    monkeypatch.setattr(client,'reqHistoricalData',legacy_wrapper)
    h=provider_module.get_intraday_bars(symbol='SYNTH',timeframe='1m',limit=40)
    assert h.completed and h.request_spec and h.contract_identity==facts.identity
    assert h.dispatched_contract_identity is None
    with pytest.raises(CompletedContextError):build(facts,history=h)


def test_dispatch_routing_identity_is_retained_and_conflicts_refuse(facts,monkeypatch):
    client=facts.chain.owner.client;owned=client.reqHistoricalData
    def conflicting_wrapper(*args,**kwargs):
        result=owned(*args,**kwargs)
        return replace(result,dispatched_contract_identity=replace(result.dispatched_contract_identity,exchange='FOREIGN'))
    monkeypatch.setattr(client,'reqHistoricalData',conflicting_wrapper)
    h=provider_module.get_intraday_bars(symbol='SYNTH',timeframe='1m',limit=40)
    assert h.status=='CONTRACT_IDENTITY_CONFLICT' and not h.completed
    assert h.dispatched_contract_identity.exchange=='FOREIGN'
    with pytest.raises(CompletedContextError):build(facts,history=h)


# ATR tests use the same genuine SDK->provider->completed-context fixture above.
from fractions import Fraction
import hashlib
from src.strategies.statistical_intraday_momentum.signal_engine.features import (
    measure_completed_atr, offline_atr_report, _context_fingerprint,
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
        default=lambda x: {'datetime': x.isoformat(), 'fold': x.fold}, allow_nan=False).encode()


def bundle_for(context, *, assessed_at=NOW):
    return dict(schema='P02_ATR_OFFLINE_V1', dataset_id='synthetic-native-callbacks', classification='SYNTHETIC',
        sessions=[dict(source_facts=context.source_facts, assessed_at=assessed_at.isoformat(),
            expected_source_sha256=context.source_fingerprint, expected_derived_sha256=context.derived_fingerprint)])


def report(bundle):
    raw = encoded(bundle)
    return offline_atr_report(raw, expected_sha256=hashlib.sha256(raw).hexdigest())


def arithmetic_context(facts, *, value=100.):
    h = facts.history
    bars = tuple(replace(b, open=value, close=value,
        high=value + (1 if i == 34 else .5), low=value - (1 if i == 34 else .5))
        for i, b in enumerate(h.bars))
    raw = tuple(dict(r, **{key: getattr(b, key) for key in ('open','high','low','close','volume')})
                for b, r in zip(bars, h.raw_source_bars))
    return build(facts, history=replace(h, bars=bars, raw_source_bars=raw, normalization_source_bars=raw))


def test_atr_seed_recurrence_and_immutable_report(facts):
    context = arithmetic_context(facts)
    result = measure_completed_atr(context, assessed_at=NOW)
    assert result.seed_usd == 1 and result.true_ranges == (1.,)*33 + (2.,)
    assert result.seed_at == (OPEN+timedelta(minutes=15)).isoformat()
    assert result.atr_usd[:-1] == (1.,)*20
    assert result.atr_usd[-1] == pytest.approx(float(Fraction(15,14)))
    assert result.atr_pct[-1] == pytest.approx(float(Fraction(15,14)))
    assert result.lower_bound_pct is None and result.upper_bound_pct is None
    assert result.admission == 'UNKNOWN' and result.eligible is False
    before = deepcopy(context.source_facts)
    raw = encoded(bundle_for(context))
    first = offline_atr_report(raw, expected_sha256=hashlib.sha256(raw).hexdigest())
    assert first == offline_atr_report(raw, expected_sha256=hashlib.sha256(raw).hexdigest())
    parsed = json.loads(first)
    assert parsed['approved_dataset'] is False and parsed['performance_claims'] is False
    row = parsed['sessions'][0]
    assert row['assessment_use'] == 'HISTORICAL_REPLAY_ONLY'
    assert row['coverage']['completed_1m'] == 35 and row['coverage']['true_range_count'] == 34
    assert row['quote_availability'] == 'VALIDATED_CONTEXT_QUOTE' and row['costs_availability'] == 'UNAVAILABLE'
    assert row['measurement']['source_sha256'] == context.source_fingerprint
    assert before == context.source_facts and raw == encoded(bundle_for(context))
    with pytest.raises(FrozenInstanceError):
        result.seed_usd = 123


def test_atr_independent_fraction_oracle_and_gap(facts):
    c = build(facts)
    bars = c['bars_1m']
    def f(x): return Fraction(str(x))
    tr = [max(f(b['high'])-f(b['low']), abs(f(b['high'])-f(p['close'])),
        abs(f(b['low'])-f(p['close']))) for p,b in zip(bars,bars[1:])]
    assert any(t > f(b['high'])-f(b['low']) for t,b in zip(tr,bars[1:]))
    state = sum(tr[:14])/14
    oracle = [state]
    for t in tr[14:]:
        state = (13*state+t)/14
        oracle.append(state)
    actual = measure_completed_atr(c, assessed_at=NOW)
    assert actual.atr_usd == pytest.approx([float(x) for x in oracle])
    assert actual.atr_pct == pytest.approx([float(100*x/f(b['close'])) for x,b in zip(oracle,bars[14:])])
    assert len(actual.member_starts) == 35  # first bar supplies predecessor, not TR


@pytest.mark.parametrize('fault', ['hash', 'mutable_bytes', 'duplicate_key', 'nan', 'schema', 'classification',
    'empty', 'too_many', 'duplicate_session', 'source_hash', 'derived_hash', 'fold', 'naive',
    'missing_fact', 'foreign', 'forming', 'stale', 'missing_quote', 'renewed_assessment', 'cost_claim'])
def test_offline_atr_invalid_inputs_refuse(facts, fault):
    c = build(facts); bundle = bundle_for(c)
    row = bundle['sessions'][0]
    if fault == 'hash':
        with pytest.raises(CompletedContextError, match='HASH'): offline_atr_report(encoded(bundle), expected_sha256='0'*64)
        return
    if fault == 'mutable_bytes':
        raw=encoded(bundle)
        with pytest.raises(CompletedContextError, match='BYTES'): offline_atr_report(bytearray(raw), expected_sha256=hashlib.sha256(raw).hexdigest())
        return
    if fault in ('duplicate_key','nan'):
        raw = b'{"schema":1,"schema":2}' if fault=='duplicate_key' else b'{"bad":NaN}'
        with pytest.raises(CompletedContextError): offline_atr_report(raw, expected_sha256=hashlib.sha256(raw).hexdigest())
        return
    if fault == 'schema': bundle['extra']=True
    if fault == 'classification': bundle['classification']='APPROVED'
    if fault == 'empty': bundle['sessions']=[]
    if fault == 'too_many': bundle['sessions']*=513
    if fault == 'duplicate_session': bundle['sessions']*=2
    if fault == 'source_hash': row['expected_source_sha256']='0'*64
    if fault == 'derived_hash': row['expected_derived_sha256']='0'*64
    if fault == 'fold': row['source_facts']['history']['bars'][0]['timestamp']={'datetime':OPEN.isoformat(),'fold':True}
    if fault == 'naive': row['assessed_at']=NOW.replace(tzinfo=None).isoformat()
    if fault == 'missing_fact': del row['source_facts']['history']['raw_source_bars']
    if fault == 'foreign': row['source_facts']['history']['dispatched_contract_identity']['con_id']=456
    if fault == 'forming': row['source_facts']['history']['completed_at_utc']=(END-timedelta(minutes=1)).isoformat()
    if fault == 'stale': row['assessed_at']=(NOW+timedelta(minutes=1)).isoformat()
    if fault == 'missing_quote': row['source_facts']['quote']['market_timestamp_utc']=None
    if fault == 'renewed_assessment': row['assessed_at']=(NOW+timedelta(seconds=1)).isoformat()
    if fault == 'cost_claim': bundle['costs']=0
    # Reach causal owner validation rather than only stopping at the input hash.
    if fault in ('missing_fact','foreign','forming','missing_quote'):
        row['expected_source_sha256']=_context_fingerprint(row['source_facts'])
    with pytest.raises(CompletedContextError): report(bundle)


def test_atr_mutation_staleness_and_overflow_refuse(facts):
    c=build(facts)
    c.payload['bars_1m'][0]['close']=1
    with pytest.raises(CompletedContextError,match='MUTATED'): measure_completed_atr(c,assessed_at=NOW)
    with pytest.raises(CompletedContextError): measure_completed_atr(build(facts),assessed_at=NOW+timedelta(minutes=1))
    # Individually finite prices may overflow TR sums/recurrence; no inf report.
    c=arithmetic_context(facts,value=1e308)
    # At this scale .5 rounds away: construct wide finite valid OHLC instead.
    source=deepcopy(c.source_facts)
    for name in ('bars','raw_source_bars','normalization_source_bars'):
        for row in source['history'][name]: row.update(high=1.7e308,low=1.)
    from src.strategies.statistical_intraday_momentum.signal_engine.features import _completed_context_values, CompletedSignalContext
    values=_completed_context_values(source,assessed_at=NOW)
    c=CompletedSignalContext(source,values,_context_fingerprint(source),_context_fingerprint(values))
    with pytest.raises(CompletedContextError,match='ARITHMETIC'): measure_completed_atr(c,assessed_at=NOW)


def test_atr_reset_no_carry_and_finite_zero_range(facts):
    first=arithmetic_context(facts)
    measured=measure_completed_atr(first,assessed_at=NOW)
    second=build(facts)
    measure_completed_atr(second,assessed_at=NOW)
    assert measure_completed_atr(first,assessed_at=NOW)==measured
    source=deepcopy(first.source_facts)
    for name in ('bars','raw_source_bars','normalization_source_bars'):
        for bar in source['history'][name]: bar.update(open=100.,high=100.,low=100.,close=100.)
    from src.strategies.statistical_intraday_momentum.signal_engine.features import _completed_context_values, CompletedSignalContext
    values=_completed_context_values(source,assessed_at=NOW)
    flat=CompletedSignalContext(source,values,_context_fingerprint(source),_context_fingerprint(values))
    result=measure_completed_atr(flat,assessed_at=NOW)
    assert result.seed_usd==0 and result.atr_usd==(0.,)*21
    assert result.eligible is False and result.admission=='UNKNOWN'
    assert measure_completed_atr(first,assessed_at=NOW)==measured


def test_offline_report_preserves_aware_raw_callbacks(facts):
    c=build(facts)
    source=deepcopy(c.source_facts)
    from src.strategies.statistical_intraday_momentum.signal_engine.features import _completed_context_values, CompletedSignalContext
    stamps=[OPEN+timedelta(minutes=i) for i in range(35)]
    source['history']['raw_bar_timestamps']=stamps
    source['history']['normalized_raw_bar_timestamps']=stamps
    for name in ('raw_source_bars','normalization_source_bars'):
        for row,stamp in zip(source['history'][name],stamps): row['date']=stamp
    values=_completed_context_values(source,assessed_at=NOW)
    c=CompletedSignalContext(source,values,_context_fingerprint(source),_context_fingerprint(values))
    value=json.loads(report(bundle_for(c)))['sessions'][0]
    assert value['raw_member_timestamps'][0]=={'datetime':OPEN.isoformat(),'fold':0}
    assert value['source_facts']['history']['request_id']==source['history']['request_id']
    assert value['measurement']['derived_sha256']==c.derived_fingerprint


@pytest.mark.parametrize('raw',[b'',b'x'*(16*1024*1024+1),b'\xff',b'['*1100])
def test_offline_bytes_bounded_and_decodable(raw):
    with pytest.raises(CompletedContextError):
        offline_atr_report(raw,expected_sha256=hashlib.sha256(raw).hexdigest())
