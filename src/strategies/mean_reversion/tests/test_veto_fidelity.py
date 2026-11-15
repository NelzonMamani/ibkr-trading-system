"""Causal real-policy/adapter/runner controls, synthetic external facts only."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.domain.quote_freshness import quote_evidence
from src.strategies.mean_reversion.adapters import (
    build_scanner_facts, build_market_regime_facts,
    policy_decision_to_model_intent,
)
from src.strategies.mean_reversion.mean_reversion_strategy_policy import (
    MeanReversionStrategyPolicy, MeanReversionPolicyConfig, MarketRegimeFacts,
)
from src.strategy.strategy_runner import StrategyRunner
from src.strategies.mean_reversion.tests.test_verify_patch_determinism import _candidate

NOW = datetime(2026, 11, 13, 16, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def config(monkeypatch):
    for name in ("FORCE_SESSION", "SESSION_OVERRIDE", "MARKET_SESSION_OVERRIDE", "FORCE_EXECUTION_WINDOW"):
        monkeypatch.delenv(name, raising=False)
    set_config_overrides({"RUN_MODE": "SIM", "SESSION_PHASE_OVERRIDE": "",
                          "MARKET_HOLIDAYS": set(), "MARKET_HALF_DAYS": set()})
    yield
    set_config_overrides(None)


def candidate(**changes):
    data = dict(vars(_candidate("MRV")))
    data.update(last_price=110., bid=109.99, ask=110.01, vwap=100., ema9=100.,
                ema20=100., atr=5., rejection_wick_up_flag=True,
                failed_breakout_up_flag=True, quote_evidence=quote_evidence(NOW, "LAST_TRADE"))
    data.update(changes)
    # Retain only coherently supplied spread for default quote facts.
    if "spread" not in changes:
        data["spread"] = 0.02
    return SimpleNamespace(**data)


def facts(row=None, snapshot=None, now=NOW, label="RTH"):
    return build_scanner_facts(row or candidate(), snapshot,
                              timestamp_utc=now.isoformat(), session_label=label)


def calm():
    # Explicit synthetic external facts, not inferred from one aggregate label.
    return MarketRegimeFacts(spy_trending_up=False, spy_trending_down=False,
                             qqq_trending_up=False, qqq_trending_down=False,
                             major_macro_event_window=False)


def decision(value=None, regime=None):
    return MeanReversionStrategyPolicy(MeanReversionPolicyConfig()).evaluate_symbol(
        value or facts(), regime or calm())


def test_genuine_complete_policy_approval_and_mapping_retains_own_contract():
    measured = facts()
    approved = decision(measured)
    assert approved.allowed and approved.reason == "APPROVED"
    assert approved.setup == "FAILED_BREAKOUT_REVERSION"
    intent = policy_decision_to_model_intent(approved, facts=measured,
        strategy_name="MeanReversionStrategy", trader_type="QUANT")
    assert intent.direction == "SHORT"
    assert intent.stop_loss_price == 110.75
    assert intent.take_profit_price == 100.5
    assert intent.invalidation_level == approved.intent.stop_price
    assert intent.pattern_name == approved.setup
    assert 0 < intent.confidence <= 1
    assert not intent.synthetic


@pytest.mark.parametrize("mode", [RunMode.SIM, RunMode.PAPER, RunMode.READ_ONLY, RunMode.LIVE])
def test_all_policy_vetoes_stay_empty_through_actual_runner(mode, monkeypatch, capsys):
    set_config_overrides({"SELECTED_STRATEGY": "mean_reversion", "RUN_MODE": mode.value,
        "MEAN_REVERSION_STRATEGY_ENABLED": True, "ROSS_MOMENTUM_STRATEGY_ENABLED": False,
        "SCANNER_DATA_SOURCE": "MOCK", "ROSS_VALIDATION_OVERRIDE_ENABLED": True,
        "LIVE_EXECUTION_PROBE_MODE": False})
    monkeypatch.setenv("FORCE_EXECUTION_WINDOW", "1")
    runner = StrategyRunner()
    # Real CandidateMetrics; a dict lacking attributes would never evaluate.
    row = replace(_candidate("VETO"), halted=True)
    result = runner.process(strategy_key="mean_reversion", watchlist=[row], snapshots={},
        session_label="RTH", timestamp_utc=NOW.isoformat(), mode=mode, session_phase="RTH_MID")
    assert result == []
    out = capsys.readouterr().out
    assert "symbol=VETO decision=SKIP" in out and "considered=1 signals=0" in out
    assert "MEAN_REVERSION_FALLBACK" not in out and "[ROSS][FORCED_INTENT]" not in out


@pytest.mark.parametrize("label,stamp,minutes", [
    ("RTH_OPEN", "2026-11-13T14:35:00+00:00", 5),
    ("RTH_MID", "2026-11-13T16:30:00+00:00", 120),
    ("RTH_LATE", "2026-11-13T20:30:00+00:00", 360),
    ("RTH", "2026-11-13T16:30:00+00:00", 120),
    ("REG", "2026-11-13T20:30:00+00:00", 360),
])
def test_actual_rth_phase_and_coarse_aliases(label, stamp, minutes):
    measured = build_scanner_facts(candidate(), None, timestamp_utc=stamp, session_label=label)
    assert measured.is_rth is True and measured.minutes_since_open == minutes


@pytest.mark.parametrize("label,stamp", [
    ("RTH_MID", "2026-11-14T16:30:00+00:00"), # weekend
    ("RTH", "2026-11-13T22:00:00+00:00"), # after actualclose
    ("RTH", "2026-11-13T13:00:00+00:00"), # premarket
    ("UNKNOWN", "2026-11-13T16:30:00+00:00"),
    ("CLOSED", "2026-11-13T16:30:00+00:00"),
    ("RTH_OPEN", "2026-11-13T16:30:00+00:00"), # phaseconflict
    ("RTH", "2026-11-13T16:30:00"), # timezoneunknown
    ("RTH", "malformed"),
])
def test_label_cannot_manufacture_session_eligibility(label, stamp):
    measured = build_scanner_facts(candidate(), None, timestamp_utc=stamp, session_label=label)
    assert measured.is_rth is False and measured.minutes_since_open is None
    assert not decision(measured).allowed


@pytest.mark.parametrize("key", ["FORCE_SESSION", "SESSION_OVERRIDE", "MARKET_SESSION_OVERRIDE"])
def test_env_override_cannot_grant_session(key, monkeypatch):
    monkeypatch.setenv(key, "RTH")
    assert not facts().is_rth


def test_config_override_holiday_and_halfday_cannot_grant_session():
    set_config_overrides({"SESSION_PHASE_OVERRIDE": "RTH_MID"})
    assert not facts().is_rth
    set_config_overrides({"MARKET_HOLIDAYS": {NOW.date()}})
    assert not facts().is_rth
    set_config_overrides({"MARKET_HALF_DAYS": {NOW.date()}})
    assert not facts(now=NOW.replace(hour=19)).is_rth


@pytest.mark.parametrize("minutes,allowed,reason", [(4, False, "TOO_EARLY_AFTER_OPEN"),
    (5, True, "APPROVED"), (360, True, "APPROVED"), (361, False, "TOO_LATE_IN_SESSION")])
def test_existing_inclusive_time_boundaries(minutes, allowed, reason):
    observed = replace(facts(), minutes_since_open=minutes)
    verdict = decision(observed)
    assert verdict.allowed is allowed and verdict.reason == reason


@pytest.mark.parametrize("change", [
    {"halted": None}, {"halted": "False"}, {"halted": True},
    {"catalyst_present": None}, {"catalyst_present": "False"}, {"catalyst_present": True},
    {"data_quality_ok": None}, {"data_quality_ok": False}, {"data_quality_ok": "True"},
    {"data_quality_flags": ["MD_STALE"]}, {"data_integrity_flags": ["FOREIGN_SECURITY"]},
    {"bid": None}, {"ask": None}, {"bid": 0.}, {"ask": 0.},
    {"bid": 110.02}, {"bid": 110.01}, {"ask": float("nan")},
    {"last_price": float("inf")}, {"last_price": True},
    {"vwap": float("nan")}, {"atr": float("nan")}, {"atr": 0.},
    {"quote_evidence": None}, {"ssr": "False"},
    {"spread": float("nan")}, {"spread": -0.1}, {"spread": 0.01},
])
def test_required_missing_invalid_and_unsafe_facts_never_look_safe(change):
    assert decision(facts(candidate(**change))).allowed is False


@pytest.mark.parametrize("status", [None, False, True])
def test_ssr_optional_selection_metadata_is_preserved_not_execution_permission(status):
    measured = facts(candidate(ssr=status))
    assert measured.ssr_flag is status
    assert decision(measured).allowed


@pytest.mark.parametrize("changes", [{"spy_trending_up": None}, {"qqq_trending_down": "False"},
    {"spy_trending_down": True}, {"major_macro_event_window": None},
    {"major_macro_event_window": True}])
def test_unknown_and_hostile_required_regime_facts_veto(changes):
    assert not decision(regime=replace(calm(), **changes)).allowed


def test_absent_aggregate_regime_cannot_supply_calm_index_facts():
    regime = build_market_regime_facts(None)
    assert regime.spy_trending_up is None and regime.major_macro_event_window is None
    assert decision(regime=regime).reason == "MACRO_EVENT_STATE_UNKNOWN"


@pytest.mark.parametrize("offset,source,flags", [
    (timedelta(seconds=1), "LAST_TRADE", ()),
    (timedelta(days=-1), "LAST_TRADE", ()),
    (timedelta(0), "UNKNOWN", ()),
    (timedelta(0), "LAST_TRADE", ("MD_TIMESTAMP_FUTURE",)),
])
def test_existing_quote_time_owner_preserves_future_stale_unknown_and_history(offset, source, flags):
    row = candidate(quote_evidence=quote_evidence(NOW + offset, source, flags))
    assert not decision(facts(row)).allowed


@pytest.mark.parametrize("change", [{"last": float("nan")}, {"last": None},
    {"ask": None}, {"bid": 120.}, {"symbol": "FOREIGN"}, {"con_id": 999},
    {"market_timestamp_utc": NOW + timedelta(seconds=1)},
    {"data_quality_flags": ("MD_STALE",)}])
def test_bad_snapshot_does_not_fallback_to_valid_candidate_quote(change):
    row = candidate(con_id=123)
    snapshot = MarketSnapshot(symbol="MRV", con_id=123, last=110., bid=109.99, ask=110.01,
        asof_utc=NOW, market_timestamp_utc=NOW, timestamp_source="LAST_TRADE")
    measured = facts(row, replace(snapshot, **change))
    assert not decision(measured).allowed


def test_valid_snapshot_owns_quote_and_preserves_selection_input():
    row = candidate(last_price=9., bid=8., ask=10., spread=2.)
    snapshot = MarketSnapshot(symbol="MRV", last=110., bid=109.99, ask=110.01,
        asof_utc=NOW, market_timestamp_utc=NOW, timestamp_source="LAST_TRADE")
    measured = facts(row, snapshot)
    assert measured.last == 110. and measured.bid == 109.99
    assert decision(measured).allowed
    assert row.last_price == 9.


@pytest.mark.parametrize("field", ["failed_breakout_up_flag", "rejection_wick_up_flag"])
def test_malformed_optional_markers_are_not_positive_evidence(field):
    row = candidate(**{**dict(failed_breakout_up_flag=False, rejection_wick_up_flag=False), field: "False"})
    assert not decision(facts(row)).allowed


@pytest.mark.parametrize("field", ["last", "atr", "vwap", "bid", "ask", "spread"])
def test_unrepresentable_integer_is_refused_without_crash(field):
    assert not decision(replace(facts(), **{field: 10 ** 1000})).allowed


def test_adapter_unrepresentable_integer_is_refused_without_crash():
    assert not decision(facts(candidate(last_price=10 ** 1000))).allowed


@pytest.mark.parametrize("field", ["volume_deceleration_flag", "failed_breakout_up_flag",
    "failed_breakout_down_flag", "rejection_wick_up_flag", "rejection_wick_down_flag", "ssr_flag"])
def test_direct_policy_does_not_treat_malformed_marker_as_support(field):
    assert decision(replace(facts(), **{field: "False"})).reason == "INVALID_SOURCE_FACTS"


def test_direct_policy_decimal_spread_is_not_rejected_for_binary_subtraction_error():
    measured = replace(facts(), spread=0.02)
    assert measured.spread != measured.ask - measured.bid
    assert decision(measured).allowed
    assert not decision(replace(measured, spread=0.01)).allowed
