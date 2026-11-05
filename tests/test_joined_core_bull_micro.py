"""SYNTHETIC joined proof; no acquisition, broker, forced Focus or prepared intent.

Reuse existing boundary/housekeeping fixtures, but retain the actual Core-created
strategy, relationship manager, full registry, qualification and selection owners.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from src.config import config_resolver
from src.core import orchestrator as core_module
from src.core.active_trade_registry import ActiveTrade
from src.ibkr.position_snapshot import BrokerPositionResult
from src.domain import quote_freshness
from src.execution import position_truth
from src.scanner import scanner_runner as ross
from src.news.news_intelligence_contract import NewsCandidate, NewsBatchResult, RetrievalDiagnostics
from src.strategy.strategy_runner import StrategyRunner
from src.strategies.ross_momentum.patterns import pattern_trace
from src.strategies.ross_momentum.patterns.pattern_trace import RossPatternFailureTraceCollector
from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
from test_news_catalyst_lifecycle_audit import lifecycle, CANDIDATE
from test_watchlist_between_scan_reassessment import reassessment
from test_pr1082_rth_watchlist_continuity import _install_runtime_harness, _row, _payload, _cadence, _reset_config
from test_pr1082_trigger_to_intent_terminal_semantics import _candles, _snapshot
from test_ross_supported_catalyst_critical_path import _saved_shape_verdict
from test_bull_flag_pipeline_end_to_end import _inputs as bull_inputs
from test_ross_pr1029_pattern_detection_certification import _micro_rows
from test_flat_top_production_handoff import forbid_collection_and_execution, forbid_io


def joined(reassessment, monkeypatch, tmp_path, *, news_fault="none", peer=False, market_fault="none", position_case=None, runtime_options=None):
    # Retain before the inherited harness temporarily stubs this class method.
    resolve_positions=core_module.CoreOrchestrator._resolve_position_truth_cycle
    c=reassessment
    life=c.life
    life.clock.current=life.clock.current.replace(hour=13,minute=35,second=30,microsecond=0)
    for module in (core_module,quote_freshness,position_truth,pattern_trace):
        monkeypatch.setattr(module,"datetime",life.clock)
    article=life.article("JPM reports earnings beat")
    if news_fault=="stale": article=life.article("JPM reports earnings beat",life.clock.current-timedelta(hours=6,microseconds=1))
    if news_fault=="expires_between": article=life.article("JPM reports earnings beat",life.clock.current-timedelta(hours=6)+timedelta(seconds=5))
    if news_fault=="nonqualifying": article=life.article("JPM market roundup")
    articles={"JPM":() if news_fault=="missing" else (article,)}
    candidates=[CANDIDATE]
    if peer:
        candidates.append(NewsCandidate("PEER",company_name="Peer Systems Inc",aliases=("Peer Systems",)))
        articles["PEER"]=(replace(life.article("PEER reports earnings beat"),symbol="PEER",
            company_name="Peer Systems Inc",aliases=("Peer Systems",)),)
    def fetch(candidates,request,policy):
        life.provider.calls+=1
        return NewsBatchResult(candidates=tuple(candidates),request=request,evidence_by_symbol=articles,
            diagnostics=RetrievalDiagnostics(retrieval_status="available",provider_status="available",provider_available=True),
            completed_at=life.clock.now(timezone.utc))
    monkeypatch.setattr(life.provider,"get_news",fetch)
    cold=life.service.get_news(tuple(candidates),life.request,life.policy)
    if news_fault not in {"missing","stale"}:
        assert cold.evidence_for_symbol("JPM")[0].published_at==article.published_at
    before=life.store.cache_path.read_bytes()
    c.row.update(last_price=10.92,bid=10.91,ask=10.93,spread_pct=100*.02/10.92,
                 dollar_volume=19656000.,session="RTH_OPEN",con_id=123)
    rows={"JPM":c.row}
    if peer: rows["PEER"]={**c.row,"symbol":"PEER","company_name":"Peer Systems Inc","con_id":456}
    if market_fault=="focus_rvol":
        rows["JPM"].update(rvol=2.,rvol_phase=2.,rvol_discovery=2.)
    def rebuild(provider,symbol,session,**kwargs):
        return dict(deepcopy(rows[symbol]),quote_timestamp_utc=kwargs["quote_override"].timestamp_utc)
    monkeypatch.setattr(ross,"_build_symbol_context",rebuild)  # Synthetic broker facts, never news/Focus flags.
    bundle=c.payload["ross_watchlist_reassessment"]
    bundle.update(date=life.clock.current.date().isoformat(),session="RTH_OPEN",contexts=list(rows.values()))
    # Scanner boundary has no prepared Focus or catalyst authority.
    scan_rows=[_row(symbol) for symbol in rows]
    for row in scan_rows:
        for key in list(vars(row)):
            if key.startswith(("catalyst", "top_news", "news_", "fresh_news", "stale_news")) or key in {"gate_checks","selection_rationale"}:
                delattr(row,key)
    payload=_payload(scan_rows,focus=[])
    payload.update(c.payload)
    core,scans,_=_install_runtime_harness(monkeypatch,[payload],**(runtime_options or {}))
    monkeypatch.delenv("FORCE_SESSION")
    overrides=dict(config_resolver._CONFIG_OVERRIDES)
    overrides.update(NEWS_ENABLED=True,NEWS_CACHE_FILE=str(life.store.cache_path),ROSS_ISSUER_QUERY_ENABLED=True,
                     SCANNER_DATA_SOURCE="IBKR",LIVE_EXECUTION_PROBE_MODE=False)
    config_resolver.set_config_overrides(overrides)
    _,policy=core._build_scanner_policy_for_strategy("ross_momentum","RTH_OPEN")
    bundle.update(policy=policy,thresholds=ross._gate_thresholds(policy,ross._resolve_runtime_thresholds(policy,"RTH_OPEN")))
    core.connection_manager._client=object()  # Synthetic already-initialized boundary, no connection/query.
    c.provider.market_data_client=core.connection_manager.optional_client
    original_scan=core_module.run_scanner_cycle
    def scan(**kwargs):
        ross._PERSISTENT_PROVIDER=c.provider
        return original_scan(**kwargs)
    monkeypatch.setattr(core_module,"run_scanner_cycle",scan)
    focus_calls=[]
    focus_rejections=[]
    original_focus=ross._select_ross_focus_contexts
    def observed_focus(contexts,news,thresholds,**kwargs):
        received=deepcopy(contexts)
        out=original_focus(contexts,news,thresholds,**kwargs)
        focus_calls.append((received,deepcopy(news),deepcopy(out)))
        focus_rejections.extend((row["symbol"],row["focus_drop_reason"]) for row in contexts if row.get("focus_drop_reason"))
        return out
    monkeypatch.setattr(ross,"_select_ross_focus_contexts",observed_focus)
    reads=[]
    def read(candidates,request,policy):
        out=life.service.get_news(candidates,request,replace(policy,network_allowed=False,
            refresh_mode="cache_only",allow_cache_write=False))
        reads.append(out)
        return out
    core._news_maintenance=NS(read=read,set_active=lambda *args:None)
    strategy=next(s for s in core.strategy_runner.strategies if s.name=="RossMomentumStrategyV1")
    assert strategy.relationship_manager is core.trade_management_engine
    assert core.risk_engine.relationship_manager is core.trade_management_engine
    assert core.execution_engine.relationship_manager is core.trade_management_engine
    strategy._failure_trace_collector=RossPatternFailureTraceCollector(evidence_root=tmp_path)
    # Restore the real class method replaced only by the inherited harness stub.
    # Do not replace/reconstruct the Core-created strategy or composition owner.
    process=StrategyRunner.process.__get__(core.strategy_runner)
    batches=[]
    def observed_process(**kwargs):
        out=process(**kwargs)
        batches.append(out)
        return out
    core.strategy_runner.process=observed_process
    core.strategy_runner.receive_watchlist_snapshot=StrategyRunner.receive_watchlist_snapshot.__get__(core.strategy_runner)
    core.strategy_runner.generate_trade_intents=StrategyRunner.generate_trade_intents.__get__(core.strategy_runner)
    inputs=[]
    results=[]
    registry_batches=[]
    original_run=strategy._pattern_registry.run
    def observed_registry(source,**kwargs):
        if market_fault=="delayed_forming_child":
            # Controlled clock latency after inputs were observed, before real
            # native registry/composition. No detector/result is substituted.
            life.clock.current+=timedelta(seconds=6)
        out=original_run(source,**kwargs)
        inputs.append(source)
        results.extend(out)
        registry_batches.append((source,out))
        return out
    monkeypatch.setattr(strategy._pattern_registry,"run",observed_registry)
    manager=core.trade_management_engine
    compositions=[]
    original_compose=manager.compose_bull_flag
    def observed_compose(pattern,source,**kwargs):
        out=original_compose(pattern,source,**kwargs)
        compositions.append((source,kwargs,out))
        return out
    monkeypatch.setattr(manager,"compose_bull_flag",observed_compose)
    children=[]
    original_micro=MicroPullbackPattern.evaluate
    def observed_micro(self,source):
        out=original_micro(self,source)
        if source.timeframe=="10s": children.append((source,out))
        return out
    monkeypatch.setattr(MicroPullbackPattern,"evaluate",observed_micro)
    end=life.clock.current.replace(second=0,microsecond=0)
    parent_rows=[(10.,10.02,9.98,10.,1000)]*42+[(b.open,b.high,b.low,b.close,b.volume) for b in bull_inputs().candles[:-1]]
    primary=_candles(parent_rows,end=end-timedelta(minutes=1))
    micro=[tuple(v+.55 if i<4 else v for i,v in enumerate(row)) for row in _micro_rows()]
    fast=_candles([(10.55,10.57,10.53,10.55,500)]*25+micro,step_seconds=10,end=end+timedelta(seconds=10))
    streams={"1m":primary,"5m":_candles(parent_rows,step_seconds=300,end=end-timedelta(minutes=5)),"10s":fast}
    if market_fault=="stale_child": streams["10s"]=[replace(b,timestamp=b.timestamp-timedelta(minutes=5)) for b in fast]
    if market_fault in {"forming_child","future_child","delayed_forming_child"}:
        # Second-cycle original clock is exactly +11s. Neither this forming
        # child nor a timestamp beyond that clock may become composed authority.
        stamp=life.clock.current+timedelta(seconds=11 if market_fault=="future_child" else 6,
                                        microseconds=1 if market_fault=="future_child" else 0)
        streams["10s"][-1]=replace(fast[-1],timestamp=stamp)
    if market_fault=="missing_identity": rows["JPM"]["con_id"]=None
    monkeypatch.setattr(pattern_trace,"get_intraday_bars",lambda *,timeframe="1m",limit=50,**kw:list(streams[timeframe])[-limit:])
    snapshot=replace(_snapshot(symbol="JPM"),last=10.92,bid=10.91,ask=10.93,
        asof_utc=life.clock.current,market_timestamp_utc=life.clock.current)
    core.market_data_snapshot_manager=NS(batch_snapshots=lambda symbols:({s:replace(snapshot,symbol=s,
        asof_utc=life.clock.current,market_timestamp_utc=life.clock.current) for s in symbols},[]))
    position_calls=[]
    truth=[]
    artifacts=[]
    evaluated=[]
    position_state={"case":position_case}
    def forbidden(*args,**kwargs): pytest.fail("five-position veto admits no artifact/risk/execution")
    if position_case is None:
        # Preserve the original saved-five-position proof unchanged.
        verdict=_saved_shape_verdict(life.clock.current)
        monkeypatch.setattr(core,"_resolve_position_truth_cycle",lambda **kwargs:verdict)
        monkeypatch.setattr(core.risk_engine,"evaluate_trade_intent",forbidden)
        monkeypatch.setattr(core_module,"build_decision_artifact",forbidden)
    else:
        # Only the external snapshot is synthetic. Real Core collection,
        # reconciliation and entry guard decide permission; no healthy verdict.
        def positions():
            case=position_state["case"]
            rows=()
            status="COMPLETE"
            account="SYNTHETIC_TEST"
            completed=life.clock.now(timezone.utc)
            if case in {"complete_matched","sign_mismatch","quantity_warning","quantity_warning_larger","partial","disconnect","wrong_account"}:
                rows=(NS(symbol="SYNTH_MATCH",position=-2 if case=="sign_mismatch" else (1 if case=="quantity_warning" else (3 if case=="quantity_warning_larger" else 2)),
                         account="OTHER_SYNTHETIC" if case=="wrong_account" else account,con_id=987),)
            if case=="five":
                rows=tuple(NS(symbol=f"SYNTH{i}",position=float(i),account=account,con_id=900+i) for i in range(1,6))
            if case=="unknown": status="UNAVAILABLE"
            if case=="partial": status="TIMEOUT"
            if case=="disconnect": status="DISCONNECTED"
            if case=="missing_completion": completed=None
            result=BrokerPositionResult(rows,status,account,completed)
            position_calls.append(result)
            return result
        client=NS() if position_case=="missing_interface" else NS(position_snapshot=positions)
        core.connection_manager._ibkr_connection_manager=NS(existing_client=client,connection_metadata=lambda: {})
        if position_case in {"complete_matched","sign_mismatch","quantity_warning","quantity_warning_larger"}:
            core.trade_registry.register_trade(ActiveTrade(symbol="SYNTH_MATCH",trader_type="SYNTHETIC",
                entry_tick=0,entry_price=10.,direction="LONG",quantity=2,stop_loss_price=9.))
        def observed_truth(**kwargs):
            verdict=resolve_positions(core,**kwargs)
            truth.append((deepcopy(core._latest_position_truth_snapshot),deepcopy(verdict)))
            return verdict
        monkeypatch.setattr(core,"_resolve_position_truth_cycle",observed_truth)
        builder=core_module.build_decision_artifact
        real_risk=core.risk_engine.evaluate_trade_intent
        def observed_artifact(**kwargs):
            artifact=builder(**kwargs)
            # TradeIntent.entry_price is attached by V1, not a dataclass field.
            # Observe the full actual object, including dynamic attributes;
            # do not mistake asdict() for complete handoff evidence.
            artifacts.append((artifact,[deepcopy(vars(i)) for i in artifact.intents]))
            return artifact
        def observed_risk(intent,**kwargs):
            received=deepcopy(vars(intent))
            decision=real_risk(intent,**kwargs)
            evaluated.append((intent,received,decision))
            return decision
        monkeypatch.setattr(core_module,"build_decision_artifact",observed_artifact)
        monkeypatch.setattr(core.risk_engine,"evaluate_trade_intent",observed_risk)
    monkeypatch.setattr(core.execution_engine,"execute_trade",forbidden)
    monkeypatch.setattr(core.execution_engine.capital_authority,"reserve",forbidden)
    monkeypatch.setattr(core.execution_engine.strategy_allocation_authority,"reserve",forbidden)
    return NS(c=c,life=life,core=core,strategy=strategy,manager=manager,scans=scans,reads=reads,batches=batches,
              inputs=inputs,results=results,registry_batches=registry_batches,compositions=compositions,
              before=before,article=article,streams=streams,cold=cold,articles=articles,rows=rows,
              children=children,focus_calls=focus_calls,focus_rejections=focus_rejections,
              position_state=position_state,position_calls=position_calls,truth=truth,artifacts=artifacts,evaluated=evaluated,
              initial_registry=deepcopy([vars(t) for t in core.trade_registry.snapshot()]),
              initial_execution_records=deepcopy(core.execution_engine.position_records))


def test_joined_native_core_composed_raw_formation_then_ownership_veto(reassessment,monkeypatch,tmp_path,capsys):
    h=joined(reassessment,monkeypatch,tmp_path)
    assert h.core.run_once() and _cadence(h.core).focus.symbols==[]
    capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)  # Advance only the synthetic clock; real cadence decides refresh.
    assert h.core.run_once()
    out=capsys.readouterr().out
    raw=[intent for batch in h.batches for intent in batch]
    assert len(raw)==1, out
    intent=raw[0]
    assert _cadence(h.core).focus.symbols==h.core.strategy_runner.last_watchlist_symbols==["JPM"]
    assert len(h.scans)==h.life.provider.calls==1
    assert h.life.store.cache_path.read_bytes()==h.before
    cached=h.reads[-1].evidence_for_symbol("JPM")[0]
    assert cached.evidence_id==h.article.evidence_id and cached.published_at==h.article.published_at
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])["JPM"]
    assert news["ross_catalyst_valid"] and news["catalyst_type"]=="EARNINGS"
    assert any([r["symbol"] for r in received]==["JPM"] and [r["symbol"] for r in selected]==["JPM"]
               for received,_,selected in h.focus_calls)
    assert intent.target_model=="BULL_FLAG_MICRO_2R_V1"
    assert intent.take_profit_price is None
    assert intent.decision_id is None and not getattr(intent,"synthetic_forced_intent",False)
    assert intent.setup_family_id=="BULL_FLAG" and intent.execution_refinement_mode=="FAST_MICRO_PULLBACK"
    assert intent.entry_price==pytest.approx(10.91)
    assert intent.stop_loss_price==intent.invalidation_level==pytest.approx(10.81)
    context=intent.relationship_context
    assert context["security_id"]=="conId:123" and context["action"]=="ENTRY"
    assert context["profile"]=="BULL_FLAG_MICRO_2R_V1" and context["parent_invalidation"]==10.63
    assert context["child_timeframe"]=="10s" and context["structure_timeframe"]=="1m"
    assert context["child_timestamp"]==h.streams["10s"][-1].timestamp.isoformat()
    source,results=h.registry_batches[-1]
    selected=results[intent.setup_metadata["canonical_result_index"]]
    assert selected.setup_family_id=="BULL_FLAG"
    assert selected.setup_metadata["relationship"]["child_id"]==context["child_id"]
    assert selected.trigger_level==intent.entry_price and selected.stop_level==intent.stop_loss_price
    assert intent.setup_metadata["execution_stream"]["observed_at_utc"]==source.observed_at_utc.isoformat()
    assert source.timeframe_provenance=={"10s":"PRESENT","1m":"PRESENT","5m":"PRESENT"}
    assert h.compositions[-1][1]["now"]==source.observed_at_utc==h.life.clock.now(timezone.utc)
    assert h.children and all(result.detected for _,result in h.children)
    assert all(b.timestamp+timedelta(seconds=10)<=child.observed_at_utc for child,_ in h.children for b in child.candles)
    parent=next(p for p in h.manager._parents.values() if p["parent_id"]==context["parent_id"])
    assert parent["security_id"]==context["security_id"] and parent["symbol"]=="JPM"
    assert parent["origin_timestamp"]==context["parent_origin"] and parent["completed_timestamp"]==context["parent_completed"]
    assert parent["consumed_children"]==[context["child_id"]]
    persisted=h.manager._persistence.fetch_management_state(h.manager._state_namespace)
    assert next(p for p in persisted["parents"].values() if p["parent_id"]==context["parent_id"])["consumed_children"]==[context["child_id"]]
    assert persisted["plans"]=={} and persisted["positions"]=={}
    # Formation consumes this event, including a rejected attempt; it is neither
    # execution reservation nor a fill/reconciled management plan.
    assert h.manager._relationship_plans=={} and h.manager.snapshot_positions()=={}
    assert h.core.execution_engine.capital_authority.active_reservations=={}
    assert h.core.execution_engine.strategy_allocation_authority.active_reservations=={}
    assert "[PIPELINE][STRATEGY_OUTPUT] count=1" in out
    assert "[PIPELINE][RISK_INPUT] intents_count=0" in out
    assert "dominant_blocking_reasons={'POSITION_TRUTH_BLOCK_NEW_ENTRIES': 1}" in out
    assert "reason=INTENT_REJECTED_BY_EXECUTION_INTEGRITY" not in out
    assert "ORDER_SUBMITTED" not in out and "[EXECUTION][SUBMIT]" not in out
    retained=asdict(intent)
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once()
    repeated=capsys.readouterr().out
    assert len([i for batch in h.batches for i in batch])==1
    assert "child_already_consumed" in repeated
    assert "[PIPELINE][STRATEGY_OUTPUT] count=0" in repeated
    assert parent["consumed_children"]==[context["child_id"]]
    assert h.manager._relationship_plans=={} and h.core.execution_engine.capital_authority.active_reservations=={}
    assert asdict(intent)==retained and h.life.provider.calls==1
    assert len(h.scans)==1 and h.life.store.cache_path.read_bytes()==h.before
    selected.setup_metadata["relationship"]["child_id"]="MUTATED_SYNTHETIC_RESULT"
    source.timeframe_provenance.clear()
    assert asdict(intent)==retained
    from src.ibkr.mutation_audit import snapshot
    assert snapshot()=={"place":0,"modify":0,"cancel":0}


@pytest.mark.parametrize("news_fault", ["missing","stale","nonqualifying","expires_between"])
def test_news_rejection_cannot_borrow_a_peer_catalyst(reassessment,monkeypatch,tmp_path,capsys,news_fault):
    h=joined(reassessment,monkeypatch,tmp_path,news_fault=news_fault,peer=True)
    if news_fault=="expires_between":
        assert (h.life.clock.current-h.article.published_at).total_seconds()==21600-5
        assert h.cold.evidence_for_symbol("JPM")[0].published_at==h.article.published_at
    assert h.core.run_once() and _cadence(h.core).focus.symbols==[]
    capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once()
    out=capsys.readouterr().out
    assert _cadence(h.core).watchlist.symbols==["JPM","PEER"]
    assert _cadence(h.core).focus.symbols==h.core.strategy_runner.last_watchlist_symbols==["PEER"]
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert not news["JPM"]["ross_catalyst_valid"] and news["PEER"]["ross_catalyst_valid"]
    assert news["JPM"]["qualification_reason"]=="no_valid_canonical_event"
    # Production cached qualification prunes the rejected issuer before quote
    # refresh/Focus. Observe the real Focus owner, do not inject a Focus list.
    assert h.focus_calls and all([r["symbol"] for r in received]==["PEER"] and
        [r["symbol"] for r in selected]==["PEER"] for received,_,selected in h.focus_calls)
    assert all(e.symbol=="JPM" and e.headline!="PEER reports earnings beat" for e in h.reads[-1].evidence_for_symbol("JPM"))
    assert h.reads[-1].evidence_for_symbol("PEER")[0].published_at==h.articles["PEER"][0].published_at
    raw=[i for batch in h.batches for i in batch]
    assert [i.symbol for i in raw]==["PEER"],out
    assert raw[0].relationship_context["security_id"]=="conId:456" and raw[0].decision_id is None
    assert {p["symbol"] for p in h.manager._parents.values()}=={"PEER"}
    assert "POSITION_TRUTH_BLOCK_NEW_ENTRIES" in out
    if news_fault=="missing": assert h.reads[-1].evidence_for_symbol("JPM")==()
    if news_fault=="nonqualifying":
        assert h.reads[-1].evidence_for_symbol("JPM")[0].headline=="JPM market roundup"
    if news_fault in {"stale","expires_between"}:
        assert h.article.published_at < h.life.clock.current-timedelta(hours=6)
        assert all(e.published_at==h.article.published_at for e in h.reads[-1].evidence_for_symbol("JPM"))
    assert h.life.provider.calls==len(h.scans)==1 and h.life.store.cache_path.read_bytes()==h.before
    assert h.manager._relationship_plans=={} and h.core.execution_engine.capital_authority.active_reservations=={}


@pytest.mark.parametrize("market_fault", ["stale_child","missing_identity","forming_child","future_child","delayed_forming_child"])
def test_qualified_news_is_not_structure_or_identity_permission(reassessment,monkeypatch,tmp_path,capsys,market_fault):
    h=joined(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    assert h.core.run_once()
    capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once()
    out=capsys.readouterr().out
    assert _cadence(h.core).focus.symbols==["JPM"]
    assert ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])["JPM"]["ross_catalyst_valid"]
    assert [i for batch in h.batches for i in batch]==[]
    reason={"missing_identity":"relationship_security_unavailable","stale_child":"pr4_input_block",
            "forming_child":"parent_armed_no_eligible_child","future_child":"parent_armed_no_eligible_child",
            "delayed_forming_child":"parent_armed_no_eligible_child"}[market_fault]
    assert reason in out
    assert "[PIPELINE][STRATEGY_OUTPUT] count=0" in out
    assert h.manager._relationship_plans=={} and h.core.execution_engine.capital_authority.active_reservations=={}
    assert not any(p["consumed_children"] for p in h.manager._parents.values())
    assert all(b.timestamp+timedelta(seconds=10)<=child.observed_at_utc for child,_ in h.children for b in child.candles)
    if market_fault=="delayed_forming_child":
        source,kwargs,_=h.compositions[-1]
        final=h.streams["10s"][-1]
        assert source.observed_at_utc < final.timestamp+timedelta(seconds=10) <= kwargs["now"]


def test_canonical_news_does_not_bypass_the_real_focus_market_gate(reassessment,monkeypatch,tmp_path,capsys):
    h=joined(reassessment,monkeypatch,tmp_path,market_fault="focus_rvol")
    assert h.core.run_once()
    capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once()
    assert _cadence(h.core).watchlist.symbols==["JPM"] and _cadence(h.core).focus.symbols==[]
    assert h.focus_calls and all([r["symbol"] for r in received]==["JPM"] and
        news["JPM"]["ross_catalyst_valid"] and selected==[] for received,news,selected in h.focus_calls)
    assert ("JPM","DROP_RVOL_FOCUS") in h.focus_rejections
    assert h.c.calls==["JPM"]  # Qualified issuer reached real broker refresh then Focus, not a news prefilter rejection.
    assert not [i for batch in h.batches for i in batch]
    assert h.inputs==h.compositions==[] and h.manager._parents=={}
    assert h.life.provider.calls==len(h.scans)==1 and h.life.store.cache_path.read_bytes()==h.before


@pytest.mark.parametrize("position_case",["complete_empty","complete_matched"])
def test_joined_core_canonical_artifact_to_actual_readonly_risk(reassessment,monkeypatch,tmp_path,capsys,position_case):
    h=joined(reassessment,monkeypatch,tmp_path,position_case=position_case)
    assert h.core.run_once() and _cadence(h.core).focus.symbols==[]
    capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once()
    out=capsys.readouterr().out
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==len(h.artifacts)==len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0]
    artifact,built=h.artifacts[0]
    assert intent is raw[0] and artifact.intents==[intent]
    assert built[0]["decision_id"] is None
    assert intent.decision_id==artifact.decision_id==decision.decision_id and intent.decision_id
    assert received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert artifact.source=="CoreOrchestrator" and artifact.run_mode=="READ_ONLY"
    assert artifact.session_phase=="OPENING_0_30" and artifact.metadata["cycle_id"]==h.core._current_cycle_id
    assert decision.symbol==intent.symbol=="JPM" and decision.strategy_name==intent.strategy_name
    assert decision.reason_code=="LIVE_READ_ONLY_BLOCK" and not decision.allowed and decision.execution_blocked
    assert decision.max_position_size==0 and decision.run_mode=="READ_ONLY"
    assert not getattr(intent,"force_execute",False) and not getattr(intent,"synthetic_forced_intent",False)
    assert "READ_ONLY mode forbids new executions" in decision.rationale
    assert "DECISION_ARTIFACT_MISSING" not in out and "RISK_APPROVED" not in out
    assert "[PIPELINE][RISK_OUTPUT] approved_count=0 blocked_count=1" in out
    assert all(s.snapshot_status=="HEALTHY" and v.healthy and not v.block_new_entries for s,v in h.truth)
    assert all(r.status=="COMPLETE" and r.completed_at is not None for r in h.position_calls)
    assert len(h.position_calls)==len(h.truth)==2
    if position_case=="complete_matched":
        assert h.truth[-1][0].matched_symbols==["SYNTH_MATCH"]
    else:
        assert h.truth[-1][0].broker_positions==h.truth[-1][0].system_positions=={}
    context=received["relationship_context"]
    source,results=h.registry_batches[-1]
    selected=results[received["setup_metadata"]["canonical_result_index"]]
    assert selected.setup_family_id==intent.setup_family_id=="BULL_FLAG"
    assert context["security_id"]=="conId:123" and context["profile"]=="BULL_FLAG_MICRO_2R_V1"
    assert context==dict(selected.setup_metadata["relationship"],action="ENTRY",warning=False,
                         relationship_id=f"{context['parent_id']}:{context['child_id']}")
    assert received["entry_price"]==selected.trigger_level==pytest.approx(10.91)
    assert received["stop_loss_price"]==selected.stop_level==pytest.approx(10.81)
    assert received["invalidation_level"]==selected.invalidation_level==pytest.approx(10.81)
    assert received["target_model"]=="BULL_FLAG_MICRO_2R_V1" and received["take_profit_price"] is None
    assert context["child_timestamp"]==h.streams["10s"][-1].timestamp.isoformat()
    assert received["setup_metadata"]["execution_stream"]["observed_at_utc"]==source.observed_at_utc.isoformat()
    parent=next(p for p in h.manager._parents.values() if p["parent_id"]==context["parent_id"])
    assert parent["consumed_children"]==[context["child_id"]]
    assert parent["security_id"]==context["security_id"] and parent["origin_timestamp"]==context["parent_origin"]
    events=h.core.event_collector.filter_by_source("CoreOrchestrator")
    assert any(e.event_type=="DECISION_ARTIFACT_CREATED" and e.payload["decision_id"]==intent.decision_id for e in events)
    assert any(e.event_type=="RISK_DECISION" and e.payload["decision_id"]==intent.decision_id and
               "LIVE_READ_ONLY_BLOCK" in e.payload["reason_codes"] for e in h.core.event_collector.filter_by_source("RiskEngine"))
    retained=deepcopy(vars(intent))
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once()
    repeated=capsys.readouterr().out
    assert len([i for batch in h.batches for i in batch])==len(h.artifacts)==len(h.evaluated)==1
    assert "child_already_consumed" in repeated and parent["consumed_children"]==[context["child_id"]]
    assert "[PIPELINE][RISK_INPUT] intents_count=0" in repeated
    persisted=h.manager._persistence.fetch_management_state(h.manager._state_namespace)
    assert next(p for p in persisted["parents"].values() if p["parent_id"]==context["parent_id"])["consumed_children"]==[context["child_id"]]
    assert persisted["plans"]==persisted["positions"]=={}
    selected.setup_metadata["relationship"]["child_id"]="MUTATED_SYNTHETIC_RESULT"
    source.timeframe_provenance.clear()
    assert vars(intent)==received==retained
    _assert_no_admission_effects(h)


def _assert_no_admission_effects(h):
    from src.ibkr.mutation_audit import snapshot
    assert snapshot()=={"place":0,"modify":0,"cancel":0}
    assert [vars(t) for t in h.core.trade_registry.snapshot()]==h.initial_registry
    assert h.core.execution_engine.position_records==h.initial_execution_records
    assert h.manager._relationship_plans=={} and h.manager.snapshot_positions()=={}
    assert h.core.execution_engine.capital_authority.active_reservations=={}
    assert h.core.execution_engine.strategy_allocation_authority.active_reservations=={}
    assert len(h.scans)==h.life.provider.calls==1 and h.life.store.cache_path.read_bytes()==h.before


@pytest.mark.parametrize("position_case",["unknown","partial","disconnect","missing_completion","missing_interface","wrong_account","sign_mismatch","five","partial_after_healthy"])
def test_joined_core_position_truth_blocks_before_artifact_and_risk(reassessment,monkeypatch,tmp_path,capsys,position_case):
    h=joined(reassessment,monkeypatch,tmp_path,
             position_case="complete_matched" if position_case=="partial_after_healthy" else position_case)
    assert h.core.run_once()
    capsys.readouterr()
    if position_case=="partial_after_healthy":
        assert h.truth[-1][1].healthy
        h.position_state["case"]="partial"
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once()
    out=capsys.readouterr().out
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==1 and raw[0].decision_id is None,out
    assert h.artifacts==h.evaluated==[]
    snapshot,verdict=h.truth[-1]
    assert not verdict.healthy and verdict.block_new_entries
    if position_case=="sign_mismatch":
        assert [m.mismatch_type for m in snapshot.mismatches]==["SIGN_MISMATCH"]
    elif position_case=="five":
        assert len(snapshot.mismatches)==verdict.critical_mismatch_count==5
        assert {m.mismatch_type for m in snapshot.mismatches}=={"BROKER_ONLY_POSITION"}
    else:
        assert snapshot.snapshot_status=="UNKNOWN" and verdict.rationale=="position_truth_unavailable"
        if position_case=="partial_after_healthy":
            assert snapshot.broker_positions["SYNTH_MATCH"].quantity==2  # Retention is not permission.
    assert "POSITION_TRUTH_BLOCK_NEW_ENTRIES" in out and "[PIPELINE][RISK_INPUT] intents_count=0" in out
    assert "DECISION_ARTIFACT_CREATED" not in out and "[PIPELINE][RISK_OUTPUT] approved_count=0 blocked_count=0" in out
    assert "reason=INTENT_REJECTED_BY_EXECUTION_INTEGRITY" not in out
    _assert_no_admission_effects(h)



@pytest.mark.parametrize("position_case,broker_quantity",[("quantity_warning",1),("quantity_warning_larger",3)])
def test_joined_core_quantity_warning_obeys_broker_magnitude_policy(reassessment,monkeypatch,tmp_path,capsys,position_case,broker_quantity):
    # Classification stays WARNING. Approved policy now vetoes broker-larger
    # magnitudes globally; broker-smaller behavior stays unchanged.
    h=joined(reassessment,monkeypatch,tmp_path,position_case=position_case)
    assert h.core.run_once()
    capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once()
    out=capsys.readouterr().out
    snapshot,verdict=h.truth[-1]
    assert snapshot.snapshot_status=="MISMATCH" and not verdict.healthy and verdict.require_reconciliation
    assert verdict.warning_mismatch_count==1 and verdict.critical_mismatch_count==0
    assert [m.mismatch_type for m in snapshot.mismatches]==["QUANTITY_MISMATCH"]
    assert verdict.block_new_entries==(broker_quantity>2)
    assert not verdict.block_exits and h.core._degraded
    if broker_quantity>2:
        raw=[i for batch in h.batches for i in batch]
        assert len(raw)==1 and raw[0].symbol=="JPM" and raw[0].decision_id is None
        assert h.artifacts==h.evaluated==[]
        assert "POSITION_TRUTH_BLOCK_NEW_ENTRIES" in out
        assert "[PIPELINE][RISK_INPUT] intents_count=0" in out
        assert snapshot.broker_positions["SYNTH_MATCH"].quantity==broker_quantity
        assert snapshot.system_positions["SYNTH_MATCH"].quantity==2
        _assert_no_admission_effects(h)
        return
    assert len(h.artifacts)==len(h.evaluated)==1,out
    decision=h.evaluated[0][2]
    assert decision.reason_code=="LIVE_READ_ONLY_BLOCK" and decision.execution_blocked
    assert snapshot.broker_positions["SYNTH_MATCH"].quantity==broker_quantity
    assert snapshot.system_positions["SYNTH_MATCH"].quantity==2
    assert decision.evaluated_limits["open_positions"]==1
    # Existing risk exposure comes from system registry quantity*entry price,
    # not max(broker,system). Mode denial is NOT proof of exposure-limit gating.
    assert decision.evaluated_limits["total_exposure"]==20.
    assert decision.evaluated_limits["trade_value"]==pytest.approx(10.91)
    assert "max_total_exposure" in decision.evaluated_limits
    assert h.core._degraded and not verdict.block_exits
    _assert_no_admission_effects(h)


@pytest.mark.parametrize("mode",["PAPER","LIVE"])
@pytest.mark.parametrize("position_case",["quantity_warning_larger","sign_mismatch","five","unknown"])
def test_mock_scanner_override_cannot_restore_position_vetoed_raw_intent(reassessment,monkeypatch,tmp_path,capsys,mode,position_case):
    # Native formation and real reconciliation. Switch mode/source only at the
    # post-formation admission seam: this isolates the existing override branch,
    # not full PAPER/LIVE startup. The already READ_ONLY mode manager and hard
    # fixture guards forbid any dispatch. No intent or verdict is fabricated.
    from src.config.runtime_config import RunMode
    h=joined(reassessment,monkeypatch,tmp_path,position_case=position_case)
    assert h.core.run_once()
    capsys.readouterr()
    process=h.core.strategy_runner.process
    def observe_formation(**kwargs):
        intents=process(**kwargs)
        h.core.run_mode=RunMode(mode)
        overrides=dict(config_resolver._CONFIG_OVERRIDES)
        overrides["SCANNER_DATA_SOURCE"]="MOCK"
        config_resolver.set_config_overrides(overrides)
        return intents
    monkeypatch.setattr(h.core.strategy_runner,"process",observe_formation)
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once()
    out=capsys.readouterr().out
    raw=[i for batch in h.batches for i in batch]
    assert len(raw)==1 and raw[0].symbol=="JPM"
    assert h.truth[-1][1].block_new_entries
    assert "POSITION_TRUTH_BLOCK_NEW_ENTRIES" in out
    assert "[E29][MOCK_OVERRIDE] forced_intent_survives_arbitration" not in out
    assert "[PIPELINE][RISK_INPUT] intents_count=0" in out
    assert h.artifacts==h.evaluated==[]
    _assert_no_admission_effects(h)
