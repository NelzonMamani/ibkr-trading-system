"""Captured observation-clock evidence; synthetic negative controls are explicit."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import pytest
from src.news.evidence_store import evidence_from_mapping
from src.news.news_intelligence_contract import NewsCandidate
from src.strategies.ross_momentum.policy import catalyst_policy as cp

FACTS=json.loads((Path(__file__).parent/'fixtures/nov13_earnings_attribution.json').read_text())['cases']
CASES=[(case,stamp) for case in FACTS for stamp in case['observation_times']]


def captured(case,stamp,monkeypatch):
    now=datetime.fromisoformat(stamp)
    monkeypatch.setattr(cp.time,'time',lambda:now.timestamp())
    item=evidence_from_mapping(case['evidence'],now=now)
    candidate=NewsCandidate(case['symbol'],company_name=case['company_name'],aliases=tuple(case['aliases']))
    return now,item,candidate


@pytest.mark.parametrize('case,stamp',CASES,ids=['DGXX-observed','SBC-first','SBC-later'])
def test_captured_observation_clock_subject_qualifies_without_cached_flags(case,stamp,monkeypatch):
    now,item,candidate=captured(case,stamp,monkeypatch)
    assert not item.is_qualifying_event_class and item.catalyst_classification is None
    before=(item.raw,item.published_at,item.headline,item.evidence_id)
    decision=cp.assess_issuer_event(candidate.symbol,item,(candidate,))
    assert decision['qualified'] and decision['catalyst_type']=='EARNINGS',decision
    assert decision['reason']=='issuer_subject_event_attributed'
    assert decision['age_seconds'] == pytest.approx((now-item.published_at).total_seconds(), abs=1e-6)
    assert (item.raw,item.published_at,item.headline,item.evidence_id)==before


@pytest.mark.parametrize('case', FACTS, ids=['DGXX', 'SBC'])
@pytest.mark.parametrize('fault', ['foreign', 'other_owner', 'question', 'preview', 'stale', 'future', 'update_only', 'dilution'])
def test_captured_subject_repair_preserves_negative_gates(case, fault, monkeypatch):
    now, item, candidate = captured(case, case['observation_times'][0], monkeypatch)
    title = item.headline
    if fault == 'foreign':
        # No company alias to independently authorize a foreign-symbol claim.
        title = f"${candidate.symbol}.TO Reports Q3 2026 Earnings"
    elif fault == 'other_owner': title += ' of Other Medical Corp'
    elif fault == 'question': title += '?'
    elif fault == 'preview': title = title.replace('Reports', 'Previews').replace('Releases', 'Previews')
    elif fault == 'stale': item = replace(item, published_at=now-timedelta(seconds=21600, microseconds=1))
    elif fault == 'future': item = replace(item, published_at=now+timedelta(microseconds=1))
    elif fault == 'update_only': item = replace(item, raw=dict(item.raw, timestamp_provenance={'selected_time_basis': 'updated'}))
    elif fault == 'dilution': title += ' and Announces Registered Direct Offering'
    item = replace(item, headline=title)
    assert not cp.assess_issuer_event(candidate.symbol, item, (candidate,))['qualified']


@pytest.mark.parametrize('title,name', [
    ('OTHER MEDICAL GROUP ($SBC) Releases Q3 2026 Earnings', 'SBC MEDICAL GROUP HOLDINGS I'),
    ('SBC MEDICAL GROUP ($SBC.TO) Releases Q3 2026 Earnings', 'SBC MEDICAL GROUP HOLDINGS I'),
    ('SBC MEDICAL GROUP Releases Q3 2026 Earnings', 'SBC MEDICAL GROUP HOLDINGS I'),
    ('SBC ($SBC) Releases Q3 2026 Earnings', 'SBC MEDICAL GROUP HOLDINGS I'),
    ('SBC MEDICAL GROUP ($SBC) Releases Q3 2026 Earnings', 'SBC MEDICAL GROUP SERVICES'),
    ('SBC MEDICAL GROUP ($SBC) and Rival Reports Q3 2026 Earnings', 'SBC MEDICAL GROUP HOLDINGS I'),
    ('Rival Reports Q3 2026 Earnings alongside SBC MEDICAL GROUP ($SBC)', 'SBC MEDICAL GROUP HOLDINGS I'),
    ('THE HOLDINGS GROUP ($SBC) Releases Q3 2026 Earnings', 'THE HOLDINGS GROUP INC'),
])
def test_parenthesized_ticker_is_neither_alias_nor_co_mention_authority(title, name, monkeypatch):
    case = FACTS[1]
    _, item, candidate = captured(case, case['observation_times'][0], monkeypatch)
    candidate = replace(candidate, company_name=name)
    item = replace(item, headline=title, company_name=name)
    assert not cp.assess_issuer_event('SBC', item, (candidate,))['qualified']


# Reuse the maintained canonical-store and actual Core cadence harness. External
# market facts are coherent synthetic controls, not the observed DGXX shortlist.
from test_watchlist_between_scan_reassessment import reassessment
from test_news_catalyst_lifecycle_audit import lifecycle


@pytest.mark.parametrize('case,stamp', CASES, ids=['DGXX-observed','SBC-first','SBC-later'])
@pytest.mark.parametrize('control', ['positive', 'stale', 'other_owner', 'dilution'])
def test_captured_canonical_evidence_reaches_actual_core_focus(reassessment, case, stamp, control, monkeypatch):
    from types import SimpleNamespace as NS
    from src.config import config_resolver
    from src.core import orchestrator as core_module
    from src.scanner import scanner_runner as ross
    from test_pr1082_rth_watchlist_continuity import _install_runtime_harness, _row, _payload, _cadence, _age_cache
    c = reassessment
    now, item, candidate = captured(case, stamp, monkeypatch)
    c.life.clock.current = now
    if control == 'stale':
        item = replace(item, published_at=now-timedelta(seconds=21600, microseconds=1))
    elif control == 'other_owner':
        item = replace(item, headline=item.headline+' of Rival Medical Corp')
    elif control == 'dilution':
        item = replace(item, headline=item.headline+' and Announces Registered Direct Offering')
    c.life.provider.articles = (item,)
    c.row.update(symbol=candidate.symbol, company_name=candidate.company_name,
                 quote_timestamp_utc=(now-timedelta(seconds=30)).isoformat())
    bundle = c.payload['ross_watchlist_reassessment']
    bundle['date'] = now.date().isoformat()
    payload = _payload([_row(candidate.symbol)], focus=[])
    payload.update(c.payload)
    core, scans, processed = _install_runtime_harness(monkeypatch, [payload])
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,
        NEWS_ENABLED=True, NEWS_CACHE_FILE=str(c.life.store.cache_path), ROSS_ISSUER_QUERY_ENABLED=True))
    _, policy = core._build_scanner_policy_for_strategy('ross_momentum', 'RTH_OPEN')
    bundle['policy'] = policy
    bundle['thresholds'] = ross._gate_thresholds(policy, ross._resolve_runtime_thresholds(policy, 'RTH_OPEN'))
    core.connection_manager._client = object()  # No transport; controlled ownership.
    c.provider.market_data_client = core.connection_manager.optional_client
    scanner_stub = core_module.run_scanner_cycle
    def scan(**kwargs):
        ross._PERSISTENT_PROVIDER = c.provider
        return scanner_stub(**kwargs)
    monkeypatch.setattr(core_module, 'run_scanner_cycle', scan)
    core._news_maintenance = NS(read=lambda candidates, request, policy:
        c.life.service.get_news(candidates, request, replace(policy, network_allowed=False,
            refresh_mode='cache_only', allow_cache_write=False)), set_active=lambda *args: None)
    assert core.run_once() and _cadence(core).focus.symbols == []
    result = c.life.service.get_news((candidate,), c.life.request, c.life.policy)
    context = ross._ross_news_contexts_from_news_intelligence_result(result)[candidate.symbol]
    assert context['ross_catalyst_valid'] is (control == 'positive')
    if result.evidence_for_symbol(candidate.symbol):
        assert result.evidence_for_symbol(candidate.symbol)[0].published_at == item.published_at
    persisted = c.life.store.cache_path.read_bytes() if c.life.store.cache_path.exists() else None
    _age_cache(_cadence(core).focus, 11)
    assert core.run_once()
    assert _cadence(core).focus.symbols == ([candidate.symbol] if control == 'positive' else [])
    assert processed == ([[candidate.symbol]] if control == 'positive' else [])
    assert len(scans) == 1 and c.life.provider.calls == 1
    assert c.calls == ([candidate.symbol] if control == 'positive' else [])
    assert (c.life.store.cache_path.read_bytes() if c.life.store.cache_path.exists() else None) == persisted


@pytest.mark.parametrize('title,name,qualified', [
    ('SBC MEDICAL GROUP & ($SBC) Releases Q3 2026 Earnings', 'SBC MEDICAL GROUP HOLDINGS I', False),
    ('SBC & MEDICAL GROUP ($SBC) Releases Q3 2026 Earnings', 'SBC MEDICAL GROUP HOLDINGS I', False),
    ('SBC MEDICAL & GROUP ($SBC) Releases Q3 2026 Earnings', 'SBC MEDICAL & GROUP HOLDINGS I', True),
    ('SBC MEDICAL GROUP & HOLDINGS I Reports Q3 Earnings', 'SBC MEDICAL GROUP HOLDINGS I', False),
    ('SBC MEDICAL GROUP HOLDINGS I Reports Q3 Earnings', 'SBC MEDICAL GROUP HOLDINGS I', True),
])
def test_coordination_cannot_be_erased_from_trusted_subject(title, name, qualified, monkeypatch):
    case = FACTS[1]
    _, item, candidate = captured(case, case['observation_times'][0], monkeypatch)
    item = replace(item, headline=title, company_name=name)
    candidate = replace(candidate, company_name=name)
    assert cp.assess_issuer_event('SBC', item, (candidate,))['qualified'] is qualified


@pytest.mark.parametrize('title,qualified', [
    ('Digi Power X & Inc Reports Q3 Earnings', False),
    ('Digi Power X, Inc. Reports Q3 Earnings', True),
    ('$DGXX Reports Q3 Earnings', True),
    ('Digi Power X Reports Q3 Earnings', True),
])
def test_legal_suffix_consumption_preserves_exact_symbols_and_issuer_names(title, qualified, monkeypatch):
    case = FACTS[0]
    _, item, candidate = captured(case, case['observation_times'][0], monkeypatch)
    assert cp.assess_issuer_event('DGXX', replace(item, headline=title), (candidate,))['qualified'] is qualified


@pytest.mark.parametrize('subject,qualified', [
    ('Johnson & Johnson', True),
    ('Johnson&Johnson Inc.', True),
    ('Johnson&Johnson', True),
    ('Johnson & Johnson & Inc.', False),
])
def test_supplied_ampersand_survives_suffix_stripping_and_normal_spacing(subject, qualified, monkeypatch):
    case = FACTS[0]
    _, item, _ = captured(case, case['observation_times'][0], monkeypatch)
    candidate = NewsCandidate('JNJ', company_name='JOHNSON & JOHNSON INC')
    item = replace(item, symbol='JNJ', company_name=candidate.company_name,
                   headline=subject+' Reports Q3 Earnings')
    assert cp.assess_issuer_event('JNJ', item, (candidate,))['qualified'] is qualified
