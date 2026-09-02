from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.event_collector import EventCollector
from src.core.orchestrator import CoreOrchestrator, load_manual_focus_config
from src.core.stop_controller import StopController
from src.execution.execution_engine import ExecutionEngine
from src.models.data_models import RiskDecision
from src.sim.price_feed import DeterministicPriceFeed
from src.strategies.ross_momentum.strategy_policy import POLICY_V2


@pytest.fixture(autouse=True)
def _reset_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FORCE_SESSION", raising=False)
    monkeypatch.delenv("MANUAL_FOCUS_ENABLED", raising=False)
    set_config_overrides(None)
    yield
    set_config_overrides(None)


def _row(symbol: str, *, catalyst: bool = False, rvol: float = 3.0, rank: float = 10.0) -> SimpleNamespace:
    status = "CONFIRMED" if catalyst else "DATA_UNAVAILABLE"
    return SimpleNamespace(
        symbol=symbol,
        session_label="RTH",
        session_phase="RTH",
        last_price=5.0,
        prev_close=4.0,
        reference_price=4.0,
        pct_change=25.0,
        gap_pct=25.0,
        volume=2_000_000,
        premarket_volume=150_000,
        rvol=rvol,
        relative_volume=rvol,
        rvol_discovery=rvol,
        rvol_phase=rvol,
        dollar_volume=10_000_000.0,
        float_millions=8.0,
        bid=5.0,
        ask=5.01,
        spread_pct=0.2,
        halted=False,
        ssr=False,
        catalyst_present=catalyst,
        catalyst_summary="fresh catalyst" if catalyst else None,
        catalyst_status=status,
        news_count=1 if catalyst else 0,
        fresh_news_count=1 if catalyst else 0,
        stale_news_count=0,
        top_news_title="confirmed catalyst" if catalyst else None,
        top_news_catalyst_tag="EARNINGS" if catalyst else None,
        news_source_mode="TEST",
        data_quality_ok=True,
        gate_checks={"price": True, "gap": True, "volume": True, "watchlist_rvol": True, "float": True},
        selection_rationale={"catalyst_status": status, "rank": rank},
        watchlist_source="LIVE_SCAN",
        promotion_reason="LIVE_SCAN",
        rank_score=rank,
        rank_components={"score": rank},
    )


def _payload(
    rows: list[SimpleNamespace],
    *,
    watchlist: list[SimpleNamespace] | None = None,
    focus: list[SimpleNamespace] | None = None,
    drop_reason_summary: dict[str, int] | None = None,
) -> dict[str, object]:
    watch_rows = list(rows if watchlist is None else watchlist)
    focus_rows = list([] if focus is None else focus)
    return {
        "candidate_metrics": list(rows),
        "universe_top_n": [{"symbol": row.symbol} for row in rows],
        "top_n_symbols": [row.symbol for row in rows],
        "candidates": list(rows),
        "watchlist_k": watch_rows,
        "watchlist_k_symbols": [row.symbol for row in watch_rows],
        "focus_m": focus_rows,
        "focus_m_symbols": [row.symbol for row in focus_rows],
        "drop_reason_summary": dict(drop_reason_summary or {}),
    }


def _install_runtime_harness(
    monkeypatch: pytest.MonkeyPatch,
    payloads: list[dict[str, object]],
    *,
    run_mode: str = "READ_ONLY",
):
    set_config_overrides(
        {
            "RUN_MODE": run_mode,
            "RUN_MODE_EFFECTIVE": run_mode,
            "EXECUTION_ENABLED": False,
            "IBKR_FALLBACK_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
            "WATCHLIST_MAX_SYMBOLS_PER_STRATEGY": 15,
            "FOCUS_MAX_SYMBOLS_PER_STRATEGY": 5,
            "TOPN_REFRESH_SECONDS": 300,
            "WATCHLIST_REFRESH_SECONDS": 60,
            "FOCUS_REFRESH_SECONDS": 10,
            "ROSS_VALIDATION_OVERRIDE_ENABLED": False,
            "MANUAL_FOCUS_ENABLED": False,
        }
    )
    monkeypatch.setenv("FORCE_SESSION", "RTH")
    monkeypatch.setattr(CoreOrchestrator, "_run_startup_validations", lambda self: None)
    monkeypatch.setattr(CoreOrchestrator, "_ensure_premarket_prep_artifact", lambda self: None)
    monkeypatch.setattr(CoreOrchestrator, "_run_force_clean_start_if_enabled", lambda self: None)
    monkeypatch.setattr(CoreOrchestrator, "_maybe_force_flatten_all_positions_on_startup", lambda self: None)
    monkeypatch.setattr(CoreOrchestrator, "_maybe_run_scheduled_prep_update", lambda self, *args, **kwargs: None)
    healthy_position_truth = SimpleNamespace(block_new_entries=False, block_exits=False, healthy=True, require_reconciliation=False)
    monkeypatch.setattr(CoreOrchestrator, "_resolve_position_truth_cycle", lambda self, as_of: healthy_position_truth)
    monkeypatch.setattr(CoreOrchestrator, "_resolve_fill_authority_cycle", lambda self: None)
    monkeypatch.setattr(CoreOrchestrator, "_resolve_lifecycle_authority_cycle", lambda self: None)
    monkeypatch.setattr(CoreOrchestrator, "_startup_recovery_allows_strategy_execution", lambda self: True)
    monkeypatch.setattr(CoreOrchestrator, "_run_position_management_tick", lambda self, now: None)
    monkeypatch.setattr(CoreOrchestrator, "_autonomous_recovery_allows_new_entries", lambda self, cycle_started_at: True)
    monkeypatch.setattr(CoreOrchestrator, "_daily_risk_allows_new_entries", lambda self, cycle_started_at: True)
    monkeypatch.setattr(CoreOrchestrator, "_resolve_tha_decisions", lambda self, **kwargs: {})
    monkeypatch.setattr("src.core.orchestrator.build_recovery_plan", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.core.orchestrator.apply_recovery_actions", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.core.orchestrator.ConnectionManager.ensure_connected", lambda self: None)

    queue = list(payloads)
    scanner_calls: list[dict[str, object]] = []

    def _scanner_cycle(**kwargs):
        scanner_calls.append(kwargs)
        if not queue:
            raise AssertionError("unexpected scanner Top N refresh")
        return queue.pop(0)

    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _scanner_cycle)
    monkeypatch.setattr("src.core.orchestrator.resolve_watchlist_selector", lambda *_args, **_kwargs: (lambda observations, _policy: observations))
    orchestrator = CoreOrchestrator()
    orchestrator.market_data_snapshot_manager = SimpleNamespace(batch_snapshots=lambda symbols: ({}, []))
    orchestrator._refresh_manual_focus_if_due = lambda *_args, **_kwargs: []
    orchestrator._resolve_manual_focus_candidates = lambda **_kwargs: ([], [])
    orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **_kwargs: None

    processed: list[list[str]] = []

    def _process(**kwargs):
        processed.append([getattr(row, "symbol", None) for row in kwargs["watchlist"]])
        return []

    orchestrator.strategy_runner.process = _process
    orchestrator.strategy_runner.generate_trade_intents = lambda *args, **kwargs: []
    return orchestrator, scanner_calls, processed


def _cadence(orchestrator: CoreOrchestrator):
    return orchestrator._strategy_cadence("ross_momentum")


def _age_cache(cache, seconds: int) -> None:
    assert cache.timestamp_utc is not None
    cache.timestamp_utc = cache.timestamp_utc - timedelta(seconds=seconds)


def test_pr1082_full_scanner_refresh_creates_authoritative_watchlist(monkeypatch, capsys) -> None:
    aaa = _row("AAA")
    bbb = _row("BBB")
    orchestrator, scanner_calls, _ = _install_runtime_harness(monkeypatch, [_payload([aaa, bbb], focus=[])])

    assert orchestrator.run_once() is True

    cadence = _cadence(orchestrator)
    assert len(scanner_calls) == 1
    assert cadence.top_n.symbols == ["AAA", "BBB"]
    assert cadence.watchlist.symbols == ["AAA", "BBB"]
    assert cadence.watchlist.authority == "SCANNER_PAYLOAD"
    assert cadence.focus.symbols == []
    assert cadence.focus.authority == "SCANNER_PAYLOAD"
    out = capsys.readouterr().out
    assert "[WATCHLIST][AUTHORITY] strategy=ross_momentum source=SCANNER_PAYLOAD" in out
    assert "symbol=AAA reason=SCANNER_KEEP_NOT_IN_WATCHLIST" not in out


def test_pr1082_watchlist_refresh_uses_cached_payload_before_topn_refresh(monkeypatch, capsys) -> None:
    aaa = _row("AAA")
    bbb = _row("BBB")
    orchestrator, scanner_calls, _ = _install_runtime_harness(monkeypatch, [_payload([aaa, bbb], focus=[])])
    assert orchestrator.run_once() is True
    capsys.readouterr()

    cadence = _cadence(orchestrator)
    _age_cache(cadence.watchlist, 61)
    _age_cache(cadence.focus, 11)

    assert orchestrator.run_once() is True

    out = capsys.readouterr().out
    assert len(scanner_calls) == 1
    assert cadence.watchlist.symbols == ["AAA", "BBB"]
    assert cadence.watchlist.authority == "CACHED_SCANNER_PAYLOAD"
    assert "source=CACHED_SCANNER_PAYLOAD reason=WITHIN_TOPN_REFRESH_WINDOW" in out
    assert "symbol=AAA reason=SCANNER_KEEP_NOT_IN_WATCHLIST" not in out
    assert "symbol=BBB reason=SCANNER_KEEP_NOT_IN_WATCHLIST" not in out


def test_pr1082_old_failure_cannot_recur_when_policy_v2_would_empty(monkeypatch, capsys) -> None:
    aaa = _row("AAA")
    bbb = _row("BBB")
    orchestrator, _, _ = _install_runtime_harness(monkeypatch, [_payload([aaa, bbb], focus=[])])

    def _policy_v2_must_not_run(*_args, **_kwargs):
        raise AssertionError("Ross continuity refresh must not rebuild Watchlist K through PolicyV2")

    monkeypatch.setattr(CoreOrchestrator, "_build_watchlist_focus_v2", _policy_v2_must_not_run)
    assert orchestrator.run_once() is True
    capsys.readouterr()

    cadence = _cadence(orchestrator)
    _age_cache(cadence.watchlist, 61)
    _age_cache(cadence.focus, 11)

    assert orchestrator.run_once() is True

    out = capsys.readouterr().out
    assert cadence.watchlist.symbols == ["AAA", "BBB"]
    assert "[PIPELINE][WATCHLIST] count=0 symbols=[]" not in out
    assert "SCANNER_KEEP_NOT_IN_WATCHLIST" not in out


def test_pr1082_scanner_can_legitimately_empty_watchlist_with_drop_reasons(monkeypatch, capsys) -> None:
    bad = _row("BAD")
    orchestrator, _, _ = _install_runtime_harness(
        monkeypatch,
        [_payload([bad], watchlist=[], focus=[], drop_reason_summary={"DROP_FLOAT_MAX": 1})],
    )

    assert orchestrator.run_once() is True

    cadence = _cadence(orchestrator)
    out = capsys.readouterr().out
    assert cadence.watchlist.symbols == []
    assert cadence.watchlist.authority == "SCANNER_PAYLOAD"
    assert "drop_reasons={'DROP_FLOAT_MAX': 1}" in out


def test_pr1082_data_unavailable_keeps_focus_empty_without_destroying_watchlist(monkeypatch, capsys) -> None:
    aaa = _row("AAA", catalyst=False)
    bbb = _row("BBB", catalyst=False)
    orchestrator, _, _ = _install_runtime_harness(monkeypatch, [_payload([aaa, bbb], focus=[])])
    assert orchestrator.run_once() is True
    capsys.readouterr()

    cadence = _cadence(orchestrator)
    _age_cache(cadence.watchlist, 61)
    _age_cache(cadence.focus, 11)

    assert orchestrator.run_once() is True

    out = capsys.readouterr().out
    assert cadence.watchlist.symbols == ["AAA", "BBB"]
    assert cadence.focus.symbols == []
    assert cadence.focus.authority == "CACHED_SCANNER_PAYLOAD"
    assert "[PIPELINE][WATCHLIST] count=2 symbols=['AAA', 'BBB']" in out
    assert "[PIPELINE][FOCUS] count=0 symbols=[]" in out


def test_pr1082_later_confirmed_catalyst_can_promote_genuine_focus(monkeypatch, capsys) -> None:
    unavailable = _row("AAA", catalyst=False)
    confirmed = _row("AAA", catalyst=True)
    orchestrator, scanner_calls, processed = _install_runtime_harness(
        monkeypatch,
        [_payload([unavailable], focus=[]), _payload([confirmed], focus=[confirmed])],
    )
    assert orchestrator.run_once() is True
    capsys.readouterr()

    cadence = _cadence(orchestrator)
    _age_cache(cadence.top_n, 301)
    _age_cache(cadence.watchlist, 61)
    _age_cache(cadence.focus, 11)

    assert orchestrator.run_once() is True

    assert len(scanner_calls) == 2
    assert cadence.watchlist.symbols == ["AAA"]
    assert cadence.focus.symbols == ["AAA"]
    assert cadence.focus.rows[0].selection_rationale["catalyst_status"] == "CONFIRMED"
    assert processed[-1] == ["AAA"]


def test_pr1082_focus_refresh_retains_authoritative_news_provenance(monkeypatch, capsys) -> None:
    aaa = _row("AAA", catalyst=True)
    orchestrator, scanner_calls, _ = _install_runtime_harness(monkeypatch, [_payload([aaa], focus=[aaa])])
    assert orchestrator.run_once() is True
    capsys.readouterr()

    cadence = _cadence(orchestrator)
    _age_cache(cadence.focus, 11)

    assert orchestrator.run_once() is True

    assert len(scanner_calls) == 1
    assert cadence.focus.authority == "CACHED_SCANNER_PAYLOAD"
    assert cadence.focus.rows[0] is aaa
    assert cadence.focus.rows[0].selection_rationale == {"catalyst_status": "CONFIRMED", "rank": 10.0}


def test_pr1082_structurally_incompatible_focus_cannot_gain_authority(monkeypatch, capsys) -> None:
    aaa = _row("AAA", catalyst=True)
    bad = _row("BAD", catalyst=True)
    orchestrator, scanner_calls, processed = _install_runtime_harness(
        monkeypatch,
        [_payload([aaa, bad], watchlist=[aaa], focus=[bad])],
    )

    assert orchestrator.run_once() is True

    cadence = _cadence(orchestrator)
    out = capsys.readouterr().out
    assert cadence.watchlist.symbols == ["AAA"]
    assert cadence.focus.symbols == []
    assert processed == []
    assert "source=SCANNER_PAYLOAD" in out
    assert "FOCUS_NOT_IN_CURRENT_WATCHLIST" in out

    _age_cache(cadence.focus, 11)
    assert orchestrator.run_once() is True

    out = capsys.readouterr().out
    assert len(scanner_calls) == 1
    assert cadence.watchlist.symbols == ["AAA"]
    assert cadence.focus.symbols == []
    assert processed == []
    assert "source=CACHED_SCANNER_PAYLOAD" in out
    assert "FOCUS_NOT_IN_CURRENT_WATCHLIST" in out

def test_pr1082_rth_cold_start_does_not_require_existing_prep_artifact(monkeypatch, tmp_path, capsys) -> None:
    set_config_overrides({"SCANNER_SYMBOLS": ["AAA"], "MANUAL_FOCUS_ENABLED": False})
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    orchestrator.prep_engine = SimpleNamespace(
        hydrate_from_artifact=lambda symbols: len(symbols),
        build_artifact_payload=lambda symbols: {"symbols": [{"symbol": symbol} for symbol in symbols]},
    )
    orchestrator._prep_next_due_at = None
    orchestrator._prep_update_thread = None
    orchestrator._prep_update_lock = Lock()
    scheduled: list[str] = []
    orchestrator._maybe_run_scheduled_prep_update = lambda _now, session: scheduled.append(session)
    written: list[dict[str, object]] = []

    def _write(payload):
        written.append(payload)
        path = tmp_path / "premarket_prep.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    monkeypatch.setattr("src.core.orchestrator.load_canonical_premarket_prep_artifact", lambda: None)
    monkeypatch.setattr("src.core.orchestrator.write_canonical_premarket_prep_artifact", _write)
    monkeypatch.setattr("src.core.orchestrator.get_current_market_session", lambda: "RTH")

    orchestrator._ensure_premarket_prep_artifact()

    out = capsys.readouterr().out
    assert written == [{"timestamp": written[0]["timestamp"], "symbols": written[0]["symbols"]}]
    assert written[0]["symbols"][0]["symbol"] == "AAA"
    assert scheduled == ["RTH"]
    assert "placeholder artifact written" in out


def test_pr1082_manual_focus_enabled_false_overrides_enabled_json(monkeypatch, tmp_path, capsys) -> None:
    path = tmp_path / "manual_focus.json"
    path.write_text(json.dumps({"enabled": True, "manual_focus": ["TMDE", "HURA"], "max_manual_symbols": 5, "live_reload_seconds": 60}), encoding="utf-8")
    monkeypatch.setattr("src.core.orchestrator.MANUAL_FOCUS_PATH", path)
    set_config_overrides({"MANUAL_FOCUS_ENABLED": False})

    cfg = load_manual_focus_config()

    out = capsys.readouterr().out
    assert cfg.enabled is False
    assert cfg.manual_focus == []
    assert cfg.configured_enabled is True
    assert cfg.configured_symbol_count == 2
    assert cfg.effective_source == "OVERRIDE:MANUAL_FOCUS_ENABLED"
    assert "enabled=False source=OVERRIDE:MANUAL_FOCUS_ENABLED symbols=[]" in out


def test_pr1082_manual_focus_enabled_true_keeps_rows_labeled_non_natural(monkeypatch, tmp_path) -> None:
    path = tmp_path / "manual_focus.json"
    path.write_text(json.dumps({"enabled": False, "manual_focus": ["TMDE"], "max_manual_symbols": 5, "live_reload_seconds": 60}), encoding="utf-8")
    monkeypatch.setattr("src.core.orchestrator.MANUAL_FOCUS_PATH", path)
    set_config_overrides({"MANUAL_FOCUS_ENABLED": True})

    cfg = load_manual_focus_config()
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    rows, rejected = orchestrator._resolve_manual_focus_candidates(
        manual_symbols=cfg.manual_focus,
        session_phase="RTH",
    )

    assert rejected == []
    assert cfg.effective_source == "OVERRIDE:MANUAL_FOCUS_ENABLED"
    assert [row.symbol for row in rows] == ["TMDE"]
    assert rows[0].watchlist_source == "MANUAL_FOCUS"
    assert rows[0].promotion_reason == "manual_focus"
    assert "MANUAL_BYPASS_STOCK_SELECTION" in rows[0].eligibility_reason_codes


def test_pr1082_read_only_execution_cannot_submit_modify_or_cancel(monkeypatch) -> None:
    set_config_overrides({"RUN_MODE": "READ_ONLY", "RUN_MODE_EFFECTIVE": "READ_ONLY", "EXECUTION_ENABLED": True})
    calls: list[str] = []

    class _Provider:
        def name(self) -> str:
            return "MUST_NOT_BE_USED"

        def is_live(self) -> bool:
            return True

        def place_order(self, request):
            calls.append("place_order")
            raise AssertionError("READ_ONLY must not place orders")

        def modify_stop_order(self, **kwargs):
            calls.append("modify_stop_order")
            raise AssertionError("READ_ONLY must not modify orders")

        def cancel_order(self, **kwargs):
            calls.append("cancel_order")
            raise AssertionError("READ_ONLY must not cancel orders")

    engine = ExecutionEngine(
        provider=_Provider(),
        trade_registry=ActiveTradeRegistry(),
        event_collector=EventCollector(),
        price_feed=DeterministicPriceFeed(),
        stop_controller=StopController(),
    )
    result = engine.execute_trade(
        RiskDecision(
            symbol="AAA",
            allowed=True,
            max_position_size=1,
            risk_level="LOW",
            rationale="test",
            strategy_name="ross_momentum",
            direction="LONG",
            intent_id="AAA-1",
        )
    )

    assert result.status == "BLOCKED"
    assert result.rationale == "LIVE_READ_ONLY_BLOCK"
    assert calls == []


def test_pr1082_ross_thresholds_and_volume_rvol_separation_remain_unchanged() -> None:
    selection = POLICY_V2.stock_selection_law
    assert selection.price_model.min_price == 1.0
    assert selection.price_model.max_price == 20.0
    assert selection.gap_model.hard_gap_threshold == 10.0
    assert selection.volume_model.min_total_volume == 1_000_000
    assert selection.volume_model.min_premarket_volume == 100_000
    assert selection.relative_volume_model.watchlist_rvol_min == 0.5
    assert selection.relative_volume_model.focus_rvol_min == 2.0
    assert selection.catalyst_model.require_catalyst is True