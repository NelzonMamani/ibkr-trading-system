from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.core_engine import orchestrator as orch
from src.core_engine.events import ExecutionEvent, RiskDecisionRecord, TradeIntentRecord
from src.core_engine.state import SessionState
from src.core.time.trading_windows import TradingWindowDecision, TradingWindowSegment


class _FakeEvaluator:
    def evaluate(self, _inputs_list):
        setup = SimpleNamespace(pattern_name="XL_HOD_BREAK", confidence=0.9)
        return SimpleNamespace(
            best_long_setup=setup,
            best_short_setup=None,
            combined_rationale_text="ok",
            all_results=[],
        )


def _scanner_payload() -> dict:
    return {
        "topn_count": 1,
        "survivors_count": 1,
        "watchlist_k_symbols": ["AAPL"],
        "focus_m_symbols": ["AAPL"],
        "watchlist": ["AAPL"],
        "focus_m": [{"symbol": "AAPL"}],
        "watchlist_k": [{"symbol": "AAPL"}],
        "drop_reason_summary": {},
        "data_quality_by_symbol": {"AAPL": []},
    }


def _risk_allow(*, intents, **_kwargs):
    return [
        RiskDecisionRecord(
            symbol=intent.symbol,
            intent_id=intent.intent_id,
            decision="ALLOW",
            max_position_size=100,
            constraints=[],
            triggered_rules=[],
            rationale="ok",
            approved_quantity=10,
            risk_allowed=True,
            entry_price=intent.entry_price,
            order_value=100.0,
        )
        for intent in intents
    ]


def test_dead_regime_blocks_executable_ross_intent(monkeypatch) -> None:
    monkeypatch.setattr(orch, "_ensure_deterministic_prep", lambda: None)
    monkeypatch.setattr(orch, "run_scanner_cycle", lambda **_: _scanner_payload())
    monkeypatch.setattr(orch, "PatternEvaluator", lambda: _FakeEvaluator())
    monkeypatch.setattr(
        orch,
        "build_trade_intents",
        lambda *_args, trigger_ready_now=False, **_kwargs: [
            TradeIntentRecord(
                symbol="AAPL",
                intent_id="intent-1",
                setup_id="XL_HOD_BREAK",
                side="LONG",
                entry="ENTRY",
                stop="STOP",
                rationale="ok",
            )
        ] if trigger_ready_now else [],
    )
    monkeypatch.setattr(orch, "resolve_entry_price", lambda *_args, **_kwargs: (10.0, "SCANNER_LAST_PRICE"))
    monkeypatch.setattr(orch, "evaluate_trade_intents", _risk_allow)
    monkeypatch.setattr(orch, "execute_intents", lambda **_: [])
    monkeypatch.setattr(
        orch,
        "resolve_market_regime_context",
        lambda _now: SimpleNamespace(regime="DEAD", asof_et=datetime.now(timezone.utc), source="TEST"),
    )

    summary = orch.run_cycle(cycle_id=1, mode_value="PAPER", forced_session_state=SessionState.REG)
    assert summary.intents == []
    assert all(event.action != "SUBMITTED" for event in summary.execution_events)


def test_paper_execution_path_still_works_inside_valid_window(monkeypatch) -> None:
    monkeypatch.setattr(orch, "_ensure_deterministic_prep", lambda: None)
    monkeypatch.setattr(orch, "run_scanner_cycle", lambda **_: _scanner_payload())
    monkeypatch.setattr(orch, "PatternEvaluator", lambda: _FakeEvaluator())
    monkeypatch.setattr(
        orch,
        "build_trade_intents",
        lambda *_args, trigger_ready_now=False, **_kwargs: [
            TradeIntentRecord(
                symbol="AAPL",
                intent_id="intent-1",
                setup_id="XL_HOD_BREAK",
                side="LONG",
                entry="ENTRY",
                stop="STOP",
                rationale="ok",
            )
        ] if trigger_ready_now else [],
    )
    monkeypatch.setattr(orch, "resolve_entry_price", lambda *_args, **_kwargs: (10.0, "SCANNER_LAST_PRICE"))
    monkeypatch.setattr(orch, "evaluate_trade_intents", _risk_allow)
    monkeypatch.setattr(
        orch,
        "execute_intents",
        lambda **kwargs: [
            ExecutionEvent(symbol=d.symbol, intent_id=d.intent_id, action="SUBMITTED", detail="ok", broker_order_id=1)
            for d in kwargs.get("decisions", [])
        ],
    )
    monkeypatch.setattr(
        orch,
        "_resolve_symbol_window_segments",
        lambda **kwargs: [
            TradingWindowSegment(
                label="TEST",
                start_dt=kwargs["now"] - timedelta(hours=1),
                end_dt=kwargs["now"] + timedelta(hours=1),
                timezone="UTC",
                source="TEST",
                tradable=True,
            )
        ],
    )

    summary = orch.run_cycle(cycle_id=2, mode_value="PAPER", forced_session_state=SessionState.REG)
    assert any(event.action == "SUBMITTED" for event in summary.execution_events)


def test_force_flat_path_is_reachable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(orch, "_ensure_deterministic_prep", lambda: None)
    monkeypatch.setattr(orch, "run_scanner_cycle", lambda **_: _scanner_payload())
    monkeypatch.setattr(orch, "PatternEvaluator", lambda: _FakeEvaluator())
    monkeypatch.setattr(orch, "build_trade_intents", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(orch, "resolve_entry_price", lambda *_args, **_kwargs: (10.0, "SCANNER_LAST_PRICE"))
    monkeypatch.setattr(orch, "evaluate_trade_intents", lambda **_: [])
    monkeypatch.setattr(orch, "execute_intents", lambda **_: [])
    monkeypatch.setattr(
        orch,
        "resolve_trading_window_decision",
        lambda *_args, **_kwargs: TradingWindowDecision(
            inside_window=True,
            allow_new_entries=False,
            allow_management=False,
            force_exit_mode=True,
            force_flat=True,
            reason="hard_flat_enforced",
        ),
    )

    orch.run_cycle(cycle_id=3, mode_value="PAPER", forced_session_state=SessionState.REG)
    out = capsys.readouterr().out
    assert "[LIFECYCLE][FORCE_FLAT] symbol=AAPL reason=trading_window_force_flat" in out
