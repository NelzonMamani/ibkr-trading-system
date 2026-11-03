"""Offline handoff contracts: synthetic OHLCV/identity, never natural acceptance."""
from dataclasses import replace
from types import SimpleNamespace
import pytest
from src.config.runtime_config import RunMode
from src.core.engines.trigger_engine import TriggerEngine
from src.setup_engine.setup_families.breakouts import ConsolidationBreakoutPattern
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from test_pr1082_trigger_to_intent_terminal_semantics import (
    _base_strategy, _inputs, _candles, _detected_three, _watchlist_row, _snapshot,
    _reset_config, FakeRegistry,
)

@pytest.mark.parametrize('target', [None, 'Range expansion'])
def test_production_selected_result_target_contract(monkeypatch,tmp_path,target):
    strategy=_base_strategy(monkeypatch,tmp_path,state='ready')
    supplied=replace(_detected_three('ready'),target_suggestion=target)
    strategy._pattern_registry=FakeRegistry([supplied])
    intents=strategy.process_watchlist(watchlist=[_watchlist_row()],snapshots={'UPC':_snapshot()},session_label='RTH',timestamp_utc='offline-target',mode=RunMode.READ_ONLY,session_phase='RTH_OPEN')
    terminal=strategy.last_symbol_terminal_outcomes['UPC']
    if target is None:
        assert intents==[]
        assert terminal['terminal_stage']=='decision'
        assert terminal['reason']=='all_detected_candidates_rejected'
        assert not terminal['trigger_evaluated'] and not terminal['trigger_ready_now']
    else:
        assert terminal['trigger_ready_now'] is True
        assert len(intents)==1
        assert intents[0].target_model==target
        assert supplied.rationale_text in intents[0].rationale
        assert intents[0].take_profit_price is None

def consolidation_inputs():
    rows=[(10.0,10.4,9.98,10.3,1200),(10.3,10.42,10.28,10.36,1000),
          (10.36,10.38,10.31,10.35,850),(10.35,10.39,10.32,10.36,840),
          (10.36,10.4,10.33,10.37,830),(10.37,10.39,10.34,10.38,820),
          (10.38,10.4,10.35,10.39,810),(10.4,10.55,10.39,10.53,1400)]
    return replace(_inputs(),candles=_candles(rows))

def test_consolidation_exports_its_own_range_contract():
    result=ConsolidationBreakoutPattern().evaluate(consolidation_inputs())
    assert result.detected
    assert result.setup_family_id=='CONSOLIDATION_BREAKOUT'
    assert result.trigger_level==10.4
    assert result.stop_level==10.31
    assert result.invalidation_level==10.31
    assert result.target_suggestion=='Range expansion'

def test_consolidation_trigger_dispatch_from_canonical_payload():
    inputs=consolidation_inputs()
    setup={'setup_family_id':'CONSOLIDATION_BREAKOUT','setup_detected':True,
           'trigger_level':10.4,'stop_level':10.31,'invalidation_level':10.31,
           'setup_metadata':{'breakout_volume_confirmed':True}}
    trigger=TriggerEngine().evaluate_triggers(symbol=inputs.symbol,candles=inputs.candles,setups=[setup],levels={},structure={})[0]
    assert trigger['trigger_ready_now'] is True
    assert trigger['trigger_reason']!='setup_trigger_mapping_missing'

@pytest.mark.parametrize('session,execution_state', [('RTH_OPEN','ready'),('RTH_OPEN','waiting'),('RTH_OPEN','missing'),('RTH_OPEN','stale'),('RTH_MID','ready')])
def test_real_consolidation_registry_to_production_intent(monkeypatch,tmp_path,session,execution_state):
    from datetime import timedelta
    strategy=_base_strategy(monkeypatch,tmp_path,state='ready')
    registry=RossPatternRegistry();registry._patterns=[ConsolidationBreakoutPattern()]
    strategy._pattern_registry=registry
    primary=list(consolidation_inputs().candles)
    end=primary[-1].timestamp
    rows=[(10.35,10.39,10.32,10.37,100)]*29
    rows.append((10.37,10.56,10.32,10.53,200) if execution_state=='ready' else (10.35,10.39,10.32,10.37,100))
    ten=_candles(rows,end=end+timedelta(seconds=10),step_seconds=10)
    if execution_state=='missing':ten=[]
    if execution_state=='stale':ten=[replace(c,timestamp=c.timestamp-timedelta(seconds=180)) for c in ten]
    data={'1m':primary,'10s':ten,'5m':_candles([(c.open,c.high,c.low,c.close,c.volume) for c in primary],step_seconds=300)}
    monkeypatch.setattr('src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars',lambda *,timeframe='1m',**kw:data[timeframe])
    intents=strategy.process_watchlist(watchlist=[_watchlist_row()],snapshots={'UPC':_snapshot()},session_label=session,session_phase=session,timestamp_utc='offline-consolidation',mode=RunMode.READ_ONLY)
    if execution_state=='ready':
        assert len(intents)==1, strategy.last_symbol_terminal_outcomes
        assert intents[0].setup_family_id=='CONSOLIDATION_BREAKOUT'
        assert intents[0].target_model=='Range expansion'
        assert intents[0].entry_price==10.4
        assert intents[0].stop_loss_price==10.31
        assert 'Tight consolidation' in intents[0].rationale
    else:
        assert intents==[]
        assert strategy.last_symbol_terminal_outcomes['UPC']['intent_emitted'] is False

@pytest.mark.parametrize('malformation',['missing_rationale','risk_off','missing_stop'])
def test_selected_result_requires_complete_entry_contract(monkeypatch,tmp_path,malformation):
    strategy=_base_strategy(monkeypatch,tmp_path,state='ready')
    chosen=replace(_detected_three(),target_suggestion='Range expansion')
    if malformation=='missing_rationale':chosen=replace(chosen,rationale_text='')
    elif malformation=='risk_off':chosen=replace(chosen,non_entry_signal=True)
    else:chosen=replace(chosen,stop_level=None,invalidation_level=None)
    strategy._pattern_registry=FakeRegistry([chosen])
    intents=strategy.process_watchlist(watchlist=[_watchlist_row()],snapshots={'UPC':_snapshot()},session_label='RTH_OPEN',session_phase='RTH_OPEN',timestamp_utc='offline-missing',mode=RunMode.READ_ONLY)
    assert intents==[]

def test_micro_pullback_numeric_contract_matches_its_detected_structure():
    from src.setup_engine.setup_families.momentum import MicroPullbackPattern
    from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet
    rows=[(10,10.2,9.95,10.15,900),(10.15,10.35,10.1,10.3,1000),
          (10.3,10.32,10.2,10.24,800),(10.24,10.25,10.16,10.18,780),
          (10.18,10.2,10.1,10.12,760),(10.15,10.42,10.14,10.4,1200)]
    inputs=replace(_inputs(),candles=_candles(rows),indicators=IndicatorSet(ema9=10.2,ema20=10.1,vwap=10.18))
    result=MicroPullbackPattern().evaluate(inputs)
    assert result.detected
    assert result.trigger_level==10.32
    assert result.invalidation_level==10.1


def test_distinct_stop_and_acceptance_invalidation_survive_trigger_handoff():
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
    inputs = consolidation_inputs()
    setup = {"setup_family_id": "PREMARKET_HIGH_BREAK", "setup_detected": True,
             "trigger_level": 10.4, "stop_level": 10.38, "invalidation_level": 10.4}
    trigger = TriggerEngine().evaluate_triggers(
        symbol=inputs.symbol, candles=inputs.candles, setups=[setup], levels={}, structure={})[0]
    assert trigger["trigger_ready_now"]
    assert trigger["invalidation_price_reference"] == 10.4
    assert trigger["stop_price_reference"] == 10.38
    assert RossMomentumStrategyV1._build_trade_from_pattern(
        SimpleNamespace(pattern_id="P_PREMARKET_HIGH_BREAK"), inputs,
        selected_trigger=trigger) == (10.4, 10.38)


@pytest.mark.parametrize("family,pattern_id,target", [
    ("MICRO_PULLBACK", "P_MICRO_PULLBACK", "Prior high / HOD"),
    ("BULL_FLAG", "P_BULL_FLAG", "Measured move"),
    ("FLAT_TOP_BREAKOUT", "P_FLAT_TOP_BREAKOUT", "Measured range expansion above flat-top resistance"),
    ("PREMARKET_HIGH_BREAK", "P_PREMARKET_HIGH_BREAK", "HOD / next resistance extension after PMH acceptance"),
    ("ORB", "P_ORB", None),
])
@pytest.mark.parametrize("state", ["ready", "not_ready", "invalidated", "missing", "stale"])
def test_core_selected_contract_through_production(monkeypatch, tmp_path, family, pattern_id, target, state):
    """Pre-produced structural contracts, not new detector or natural certification."""
    from datetime import timedelta
    from test_pr1082_trigger_to_intent_terminal_semantics import _bars
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    contract = replace(_detected_three(), setup_id=pattern_id, setup_family_id=family,
                       pattern_name=family, target_suggestion=target,
                       trigger_level=10.44, stop_level=10.08, invalidation_level=10.08,
                       setup_metadata={}, rationale_text="Offline selected structure contract")
    strategy._pattern_registry = FakeRegistry([contract])
    def bars(*, timeframe="1m", **kwargs):
        rows = _bars(state if state in {"not_ready", "invalidated"} else "ready", timeframe)
        if timeframe == "10s" and state == "missing":
            return []
        if timeframe == "10s" and state == "stale":
            return [replace(c, timestamp=c.timestamp-timedelta(seconds=180)) for c in rows]
        return rows
    monkeypatch.setattr("src.strategies.ross_momentum.patterns.pattern_trace.get_intraday_bars", bars)
    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()], snapshots={"UPC": _snapshot()},
        session_label="RTH_OPEN", session_phase="RTH_OPEN", timestamp_utc="offline-core",
        mode=RunMode.READ_ONLY)
    terminal = strategy.last_symbol_terminal_outcomes["UPC"]
    if target is None:
        assert intents == []
        assert terminal["terminal_stage"] == "decision"
        assert terminal["reason"] == "all_detected_candidates_rejected"
        assert not terminal["trigger_evaluated"] and not terminal["trigger_ready_now"]
    elif state == "ready":
        assert terminal["trigger_ready_now"] is True
        if target is not None:
            assert len(intents) == 1, terminal
            assert intents[0].target_model == target
            assert intents[0].entry_price == 10.44
            assert intents[0].stop_loss_price == 10.08
    else:
        assert intents == []
        assert terminal["trigger_ready_now"] is False


def test_target_contract_is_not_borrowed_across_symbols(monkeypatch, tmp_path):
    strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
    class SymbolRegistry(FakeRegistry):
        def run(self, inputs, **kwargs):
            self.results = [replace(_detected_three(), target_suggestion=(
                "OFFLINE_BBB_TARGET" if inputs.symbol == "BBB" else None))]
            return super().run(inputs, **kwargs)
    strategy._pattern_registry = SymbolRegistry([])
    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row(symbol=s) for s in ("BBB", "AAA")],
        snapshots={s: _snapshot(symbol=s) for s in ("BBB", "AAA")},
        session_label="RTH_OPEN", session_phase="RTH_OPEN", timestamp_utc="offline-isolation",
        mode=RunMode.READ_ONLY)
    assert [intent.symbol for intent in intents] == ["BBB"]
    assert intents[0].target_model == "OFFLINE_BBB_TARGET"
    assert strategy.last_symbol_terminal_outcomes["AAA"]["reason"] == "all_detected_candidates_rejected"
    assert strategy.last_symbol_terminal_outcomes["AAA"]["terminal_stage"] == "decision"


@pytest.fixture(autouse=True)
def _forbid_broker_activity(monkeypatch):
    from ibapi.client import EClient
    def forbidden(*args, **kwargs):
        raise AssertionError('Selected-setup controls forbid broker activity')
    for name in ('connect', 'placeOrder', 'cancelOrder', 'reqGlobalCancel',
                 'reqMktData', 'reqHistoricalData', 'reqPositions', 'reqAllOpenOrders'):
        monkeypatch.setattr(EClient, name, forbidden)


def _viable_micro_contract():
    from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
    from test_ross_pr1029_pattern_detection_certification import _inputs, _micro_rows
    result = MicroPullbackPattern().evaluate(_inputs(symbol='UPC', rows=_micro_rows()))
    assert result.detected and result.target_suggestion == 'Prior high / HOD'
    return result


def _run_contracts(monkeypatch, tmp_path, contracts):
    strategy = _base_strategy(monkeypatch, tmp_path, state='ready')
    strategy._pattern_registry = FakeRegistry(contracts)
    decisions = []
    original = strategy._decision_engine.compute_decision
    def compute(**kwargs):
        result = original(**kwargs)
        decisions.append(result)
        return result
    monkeypatch.setattr(strategy._decision_engine, 'compute_decision', compute)
    intents = strategy.process_watchlist(
        watchlist=[_watchlist_row()], snapshots={'UPC': _snapshot()},
        session_label='RTH_OPEN', session_phase='RTH_OPEN', timestamp_utc='offline-entry-contract',
        mode=RunMode.READ_ONLY)
    return strategy, intents, decisions


@pytest.mark.parametrize('reverse', [False, True])
def test_incomplete_high_ranked_candidate_cannot_starve_viable_micro(monkeypatch, tmp_path, reverse):
    # Synthetic arbitration score, actual positive Micro detector contract.
    micro = _viable_micro_contract()
    incomplete = replace(_detected_three(), confidence=.99, target_suggestion=None)
    contracts = [micro, incomplete] if reverse else [incomplete, micro]
    strategy, intents, decisions = _run_contracts(monkeypatch, tmp_path, contracts)
    assert len(intents) == 1, strategy.last_symbol_terminal_outcomes
    intent = intents[0]
    assert intent.setup_family_id == 'MICRO_PULLBACK'
    assert intent.target_model == micro.target_suggestion
    assert intent.entry_price == micro.trigger_level
    assert intent.stop_loss_price == micro.stop_level
    assert micro.rationale_text in intent.rationale
    assert intent.take_profit_price is None  # No numeric target invented.
    assert decisions[0]['selected_pattern_id'] == micro.setup_id
    assert any(r['pattern_id'] == incomplete.setup_id and r['reason'] == 'missing_target'
               for r in decisions[0]['rejected_candidates'])


def test_multiple_intrinsic_failures_record_each_reason_before_selection(monkeypatch, tmp_path):
    micro = _viable_micro_contract()
    base = _detected_three()
    invalid = [replace(base, setup_id='P_THREE_BAR_PULLBACK', target_suggestion=None, confidence=.99),
               replace(base, setup_id='P_SECOND_PULLBACK', setup_family_id='SECOND_PULLBACK', rationale_text='', confidence=.98),
               replace(base, setup_id='P_BULL_FLAG', setup_family_id='BULL_FLAG', stop_level=None, invalidation_level=None,
                       stop_suggestion=None, confidence=.97)]
    strategy, intents, decisions = _run_contracts(monkeypatch, tmp_path, [*invalid, micro])
    assert len(intents) == 1 and intents[0].setup_family_id == 'MICRO_PULLBACK'
    reasons = {r['pattern_id']:r['reason'] for r in decisions[0]['rejected_candidates']}
    assert reasons['P_THREE_BAR_PULLBACK'] == 'missing_target'
    assert reasons['P_SECOND_PULLBACK'] == 'missing_rationale'
    assert reasons['P_BULL_FLAG'] == 'missing_stop'


@pytest.mark.parametrize('reverse', [False, True])
def test_all_intrinsically_incomplete_candidates_return_existing_no_entry(monkeypatch, tmp_path, reverse):
    first = replace(_detected_three(), target_suggestion=None)
    second = replace(first, setup_id='P_SECOND_PULLBACK', setup_family_id='SECOND_PULLBACK',
                     rationale_text='')
    strategy, intents, decisions = _run_contracts(monkeypatch, tmp_path,
                                                [second, first] if reverse else [first, second])
    assert intents == []
    assert decisions[0]['decision_state'] == 'CANDIDATE_REJECTED_INSUFFICIENT_QUALITY'
    assert decisions[0]['selected_pattern_id'] is None
    assert {r['reason'] for r in decisions[0]['rejected_candidates']} == {'missing_target','missing_rationale'}
    terminal = strategy.last_symbol_terminal_outcomes['UPC']
    assert terminal['outcome'] == 'SETUP_FOUND_DECISION_REJECTED'
    assert terminal['terminal_stage'] == 'decision' and not terminal['intent_emitted']


@pytest.mark.parametrize('reverse', [False, True])
def test_entry_filter_keeps_existing_valid_ranking_and_one_winner(reverse):
    from src.core.engines.decision_engine import DecisionEngine
    from src.strategies.ross_momentum.decision_policy import validate_entry_contract
    micro = _viable_micro_contract()
    other = replace(_detected_three(), confidence=.99)
    contracts = [micro, other] if reverse else [other, micro]
    kwargs = dict(symbol='UPC', levels={}, structure={'trend':'UP'}, setups=[],
                  pattern_results=contracts, session_context='RTH')
    original = DecisionEngine().compute_decision(**kwargs)
    filtered = DecisionEngine().compute_decision(**kwargs, entry_contract_validator=validate_entry_contract)
    assert filtered.pop('selected_candidate_index') == contracts.index(other)
    assert filtered == original
    assert filtered['selected_pattern_id'] == other.setup_id
    assert len(filtered['rejected_candidates']) == 1
    assert filtered['rejected_candidates'][0]['reason'] == 'dropped_lower_priority_compatible_candidate'


@pytest.mark.parametrize('kind', ['risk_off', 'context', 'opposing'])
def test_entry_completeness_cannot_remove_suppression_or_conflict(kind):
    from src.core.engines.decision_engine import DecisionEngine
    from src.strategies.ross_momentum.decision_policy import validate_entry_contract
    from src.strategies.ross_momentum.patterns.pattern_types import Direction
    micro = _viable_micro_contract()
    other = replace(_detected_three(), target_suggestion=None)
    if kind == 'risk_off':
        other = replace(other, setup_id='P_PARABOLIC_EXHAUSTION', setup_family_id='PARABOLIC_EXHAUSTION',
                        non_entry_signal=True, signal_class='RISK_OFF')
    elif kind == 'context':
        other = replace(other, non_entry_signal=True, signal_class='CONTEXT')
    else:
        other = replace(other, direction=Direction.SHORT)
    kwargs = dict(symbol='UPC', levels={}, structure={'trend':'UP'}, setups=[],
                  pattern_results=[other, micro], session_context='RTH')
    original = DecisionEngine().compute_decision(**kwargs)
    filtered = DecisionEngine().compute_decision(**kwargs, entry_contract_validator=validate_entry_contract)
    if kind == 'context':
        assert filtered.pop('selected_candidate_index') == 1
    assert filtered == original
    if kind == 'context':
        assert filtered['selected_pattern_id'] == micro.setup_id
        assert filtered['rejected_candidates'][0]['reason'] == 'non_entry_signal'
    else:
        assert filtered['selected_pattern_id'] is None
        expected = 'risk_off_suppression_active' if kind == 'risk_off' else 'rejected_true_conflict_opposing_direction'
        assert any(r['reason']==expected for r in filtered['rejected_candidates'])


def test_complete_selected_family_does_not_fall_back_after_unconfirmed_trigger(monkeypatch, tmp_path):
    micro = _viable_micro_contract()
    waiting = replace(_detected_three(), confidence=.99, trigger_level=10.9)
    strategy, intents, decisions = _run_contracts(monkeypatch, tmp_path, [waiting, micro])
    assert intents == []
    assert decisions[0]['selected_pattern_id'] == waiting.setup_id
    terminal = strategy.last_symbol_terminal_outcomes['UPC']
    assert not terminal['trigger_ready_now'] and not terminal['intent_emitted']
    assert terminal['selected_pattern_id'] == waiting.setup_id


@pytest.mark.parametrize('malformation,reason', [('target','missing_target'), ('rationale','missing_rationale'),
                                               ('stop','missing_stop'), ('geometry','invalid_risk_geometry')])
def test_shared_entry_contract_validator_keeps_actual_intrinsic_failure(malformation, reason):
    from src.strategies.ross_momentum.decision_policy import validate_entry_contract
    contract = _viable_micro_contract()
    if malformation == 'target': contract=replace(contract,target_suggestion=None)
    elif malformation == 'rationale': contract=replace(contract,rationale_text='')
    elif malformation == 'stop': contract=replace(contract,stop_level=None,invalidation_level=None,stop_suggestion=None)
    else: contract=replace(contract,stop_level=contract.trigger_level,invalidation_level=contract.trigger_level)
    assert validate_entry_contract(contract)==(False,reason)


def test_entry_contract_validator_accepts_existing_mapping_fields_without_exporting_source():
    from dataclasses import asdict
    import json
    from src.core.engines.decision_engine import DecisionEngine
    from src.strategies.ross_momentum.decision_policy import validate_entry_contract
    contract = _viable_micro_contract()
    mapped = asdict(contract)
    assert validate_entry_contract(mapped) == validate_entry_contract(contract) == (True,'ok')
    result = DecisionEngine().compute_decision(symbol='UPC',levels={},structure={},setups=[],
        pattern_results=[mapped],entry_contract_validator=validate_entry_contract)
    assert result['selected_pattern_id'] == contract.setup_id
    assert '_entry_contract_source' not in json.dumps(result)


def test_entry_validator_fault_fails_closed_without_selecting_another_candidate():
    from src.core.engines.decision_engine import DecisionEngine
    calls = []
    def failed(candidate):
        calls.append(candidate.setup_id)
        raise RuntimeError('synthetic validator failure')
    with pytest.raises(RuntimeError, match='synthetic validator failure'):
        DecisionEngine().compute_decision(symbol='UPC',levels={},structure={},setups=[],
            pattern_results=[_detected_three(),_viable_micro_contract()],entry_contract_validator=failed)
    assert calls == ['P_THREE_BAR_PULLBACK']


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('failure', ['target', 'not_detected'])
def test_rejected_same_id_occurrence_cannot_replace_selected_contract(monkeypatch, tmp_path, reverse, failure):
    selected = replace(_viable_micro_contract(), setup_metadata={'review_binding':'selected'})
    rejected = replace(selected, target_suggestion=None if failure=='target' else selected.target_suggestion,
                       detected=failure!='not_detected', confidence=.99,
                       trigger_level=10.30,stop_level=10.10,invalidation_level=10.10,
                       rationale_text='REJECTED_OCCURRENCE_CANARY',
                       setup_metadata={'review_binding':'rejected'})
    contracts=[selected,rejected] if reverse else [rejected,selected]
    strategy,intents,decisions=_run_contracts(monkeypatch,tmp_path,contracts)
    assert len(intents)==1,strategy.last_symbol_terminal_outcomes
    intent=intents[0]
    assert intent.entry_price==selected.trigger_level
    assert intent.stop_loss_price==selected.stop_level
    assert intent.target_model==selected.target_suggestion
    assert intent.confidence==selected.confidence
    assert selected.rationale_text in intent.rationale
    assert 'REJECTED_OCCURRENCE_CANARY' not in intent.rationale


@pytest.mark.parametrize('same_id',[False,True])
def test_error_trace_without_result_cannot_shift_selected_confidence(monkeypatch, tmp_path, same_id):
    from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternTrace
    selected=_viable_micro_contract()
    rejected=replace(_detected_three(),target_suggestion=None,confidence=.99)
    strategy=_base_strategy(monkeypatch,tmp_path,state='ready')
    class FailedThenResults(FakeRegistry):
        def run(self,inputs,*,trace_context=None,trace_collector=None):
            trace=RossPatternTrace(symbol=inputs.symbol,pattern_id=selected.setup_id if same_id else 'P_OFFLINE_FAILED_DETECTOR',
                                  pattern_name='Offline failed detector',invoked=True,cycle_id='offline',
                                  strategy_key='ross_momentum',session_label='RTH_OPEN',
                                  session_phase='RTH_OPEN',runtime_mode='READ_ONLY',symbol_source='watchlist')
            trace.detected=False
            trace.final_outcome='ERROR'
            if trace_collector:trace_collector(trace)
            return super().run(inputs,trace_context=trace_context,trace_collector=trace_collector)
    strategy._pattern_registry=FailedThenResults([selected,rejected])
    intents=strategy.process_watchlist(watchlist=[_watchlist_row()],snapshots={'UPC':_snapshot()},
        session_label='RTH_OPEN',session_phase='RTH_OPEN',timestamp_utc='offline-error-trace',mode=RunMode.READ_ONLY)
    if same_id:
        assert intents==[]
        assert strategy.last_symbol_terminal_outcomes['UPC']['reason']=='selected_contract_binding_unavailable'
    else:
        assert len(intents)==1,strategy.last_symbol_terminal_outcomes
        assert intents[0].confidence==selected.confidence


@pytest.mark.parametrize('reverse',[False,True])
def test_selected_occurrence_binding_retains_eligible_same_id_source(monkeypatch,tmp_path,reverse):
    selected=replace(_viable_micro_contract(),confidence=.8,setup_metadata={'review_binding':'selected'})
    other=replace(selected,confidence=.65,trigger_level=10.30,stop_level=10.10,
                  invalidation_level=10.10,rationale_text='UNSELECTED_ELIGIBLE_CANARY',
                  setup_metadata={'review_binding':'other'})
    contracts=[other,selected] if reverse else [selected,other]
    strategy,intents,decisions=_run_contracts(monkeypatch,tmp_path,contracts)
    assert len(intents)==1,strategy.last_symbol_terminal_outcomes
    intent=intents[0]
    assert intent.confidence==selected.confidence
    assert intent.entry_price==selected.trigger_level and intent.stop_loss_price==selected.stop_level
    assert intent.target_model==selected.target_suggestion
    assert selected.rationale_text in intent.rationale and 'UNSELECTED_ELIGIBLE_CANARY' not in intent.rationale
    bound=strategy._resolve_selected_contract(decision=decisions[0],pattern_results=contracts)
    assert bound is selected and bound.setup_metadata=={'review_binding':'selected'}


@pytest.mark.parametrize('bad_index',[True,-1,2,'0'])
def test_invalid_occurrence_binding_never_substitutes_a_contract(bad_index):
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
    selected=_viable_micro_contract()
    decision={'selected_pattern_id':selected.setup_id,'selected_candidate_index':bad_index}
    assert RossMomentumStrategyV1._resolve_selected_contract(decision=decision,pattern_results=[selected]) is None


def test_ambiguous_legacy_binding_fails_closed_without_removing_registry_duplicates():
    from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1
    selected=_viable_micro_contract()
    other=replace(selected,target_suggestion=None)
    assert RossMomentumStrategyV1._resolve_selected_contract(
        decision={'selected_pattern_id':selected.setup_id},pattern_results=[other,selected]) is None
