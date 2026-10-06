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
    assert terminal['trigger_ready_now'] is True
    if target is None:
        assert intents==[]
        assert terminal['reason']=='missing_target'
    else:
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
    if state == "ready":
        assert terminal["trigger_ready_now"] is True
        if target is None:
            assert intents == []
            assert terminal["reason"] == "missing_target"
        else:
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
    assert strategy.last_symbol_terminal_outcomes["AAA"]["reason"] == "missing_target"
