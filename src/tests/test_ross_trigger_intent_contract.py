from __future__ import annotations

import ast
from types import SimpleNamespace

from src.core_engine.events import ExecutionEvent, RiskDecisionRecord, TradeIntentRecord
from src.core.pricing.price_resolver import PriceResolutionError
from src.core_engine.orchestrator import run_cycle
from src.core_engine.state import SessionState
from src.strategies.ross_momentum.decision_policy import build_trade_intents
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluationSummary
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternFamily, PatternResult


def _pattern_result(*, detected: bool = True, confidence: float = 0.9, entry_zone: str | None = "Breakout") -> PatternResult:
    return PatternResult(
        setup_id="setup-1",
        pattern_name="Gap Go",
        pattern_family=PatternFamily.BREAKOUT,
        detected=detected,
        direction=Direction.LONG,
        confidence=confidence,
        setup_quality_tags=[],
        entry_zone=entry_zone,
        stop_suggestion="Below candle low",
    )


def _summary(*, detected: bool = True, confidence: float = 0.9, entry_zone: str | None = "Breakout") -> PatternEvaluationSummary:
    result = _pattern_result(detected=detected, confidence=confidence, entry_zone=entry_zone)
    return PatternEvaluationSummary(
        all_results=[result],
        best_long_setup=result if detected else None,
        best_short_setup=None,
        conflict_flag=False,
        combined_rationale_text="test",
        veto_flags=[],
    )


def test_trigger_ready_true_emits_intent_or_explicit_block() -> None:
    intents = build_trade_intents(
        strategy_id="RossMomentumStrategy",
        symbol="ABCD",
        summary=_summary(detected=True, confidence=0.2, entry_zone=None),
        trigger_ready_now=True,
    )
    assert intents, "trigger_ready_now=True must produce an intent for valid setup inputs"


def test_trigger_authority_aligns_strategy_trace(capsys) -> None:
    build_trade_intents(
        strategy_id="RossMomentumStrategy",
        symbol="ABCD",
        summary=_summary(detected=True, confidence=0.2, entry_zone=None),
        trigger_ready_now=True,
    )
    out = capsys.readouterr().out
    assert "trigger_fired=True" in out


def test_trigger_without_intent_is_explicitly_blocked(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (5.0, "IBKR_SNAPSHOT"))
    monkeypatch.setattr("src.core_engine.orchestrator.build_trade_intents", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("src.core_engine.orchestrator.evaluate_trade_intents", lambda **_: [])
    monkeypatch.setattr("src.core_engine.orchestrator.execute_intents", lambda **_: [])

    run_cycle(cycle_id=1, mode_value="PAPER", forced_session_state=SessionState.PRE)
    out = capsys.readouterr().out
    assert "NO_STRATEGY_INTENT" not in out
    assert "reason=BLOCKED_BY_POLICY" in out


def test_intent_risk_execution_pipeline_end_to_end(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (5.0, "IBKR_SNAPSHOT"))
    monkeypatch.setattr(
        "src.core_engine.orchestrator.build_trade_intents",
        lambda *args, **_kwargs: [
            TradeIntentRecord(
                symbol=args[1],
                intent_id="intent-ABCD",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price_source="IBKR_SNAPSHOT",
            )
        ],
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.evaluate_trade_intents",
        lambda **_: [
            RiskDecisionRecord(
                symbol="ABCD",
                intent_id="intent-ABCD",
                decision="ALLOW",
                max_position_size=100,
                constraints=[],
                triggered_rules=[],
                rationale="PASS",
                approved_quantity=1,
            )
        ],
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.execute_intents",
        lambda **_: [
            ExecutionEvent(
                symbol="ABCD",
                intent_id="intent-ABCD",
                action="SUBMITTED",
                detail="submitted",
                broker_order_id=42,
            )
        ],
    )
    summary = run_cycle(cycle_id=1, mode_value="PAPER", forced_session_state=SessionState.PRE)
    assert len(summary.intents) >= 1
    assert any(decision.decision == "ALLOW" for decision in summary.risk_decisions)
    assert any(event.action == "SUBMITTED" for event in summary.execution_events)


def test_cycle_summary_logs_root_cause(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (5.0, "SCANNER_LAST_PRICE"))
    monkeypatch.setattr("src.core_engine.orchestrator.evaluate_trade_intents", lambda **_: [])
    monkeypatch.setattr("src.core_engine.orchestrator.execute_intents", lambda **_: [])

    run_cycle(cycle_id=1, mode_value="PAPER", forced_session_state=SessionState.PRE)
    out = capsys.readouterr().out
    assert "[ROSS][CYCLE_ROOT_CAUSE]" in out
    assert "[PIPELINE][CYCLE_SUMMARY]" in out
    assert "[PIPELINE][BLOCKER] symbol=ABCD" in out


def test_cycle_continues_after_price_authority_block_and_emits_price_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["BAD", "GOOD"],
            "focus_m_symbols": ["BAD", "GOOD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "BAD", "last_price": 5.0}, {"symbol": "GOOD", "last_price": 10.0}],
        },
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.resolve_entry_price",
        lambda symbol, *_args, **_kwargs: (5.0, "SCANNER_LAST_PRICE") if symbol == "BAD" else (10.0, "IBKR_SNAPSHOT"),
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.build_trade_intents",
        lambda *args, **_kwargs: [
            TradeIntentRecord(
                symbol=args[1],
                intent_id=f"intent-{args[1]}",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price_source="IBKR_SNAPSHOT",
            )
        ],
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.evaluate_trade_intents",
        lambda **_: [
            RiskDecisionRecord(
                symbol="GOOD",
                intent_id="intent-GOOD",
                decision="ALLOW",
                max_position_size=100,
                constraints=[],
                triggered_rules=[],
                rationale="PASS",
                approved_quantity=1,
            )
        ],
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.execute_intents",
        lambda **_: [
            ExecutionEvent(
                symbol="GOOD",
                intent_id="intent-GOOD",
                action="SUBMITTED",
                detail="submitted",
                broker_order_id=42,
            )
        ],
    )

    run_cycle(cycle_id=1, mode_value="PAPER", forced_session_state=SessionState.PRE)
    out = capsys.readouterr().out
    assert "[PIPELINE][INTENT] symbol=BAD created=true forced=false intent_id=intent-BAD" in out
    assert "[INTENT][CREATED] symbol=BAD price=None" in out
    assert "[EXECUTION][SUBMIT_RESULT] symbol=GOOD submitted=True" in out
    assert "[CYCLE][PRICE_AUTHORITY_SUMMARY]" in out


def test_ibkr_missing_price_is_wait_state_not_invalid_input_block(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.resolve_entry_price",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PriceResolutionError("ABCD", "NO_IBKR_PRICE_AVAILABLE")),
    )
    monkeypatch.setattr("src.core_engine.orchestrator._wait_for_ibkr_snapshot_for_symbol", lambda **_: False)
    monkeypatch.setattr("src.core_engine.orchestrator.evaluate_trade_intents", lambda **_: [])
    monkeypatch.setattr("src.core_engine.orchestrator.execute_intents", lambda **_: [])

    run_cycle(cycle_id=1, mode_value="LIVE", forced_session_state=SessionState.PRE)
    out = capsys.readouterr().out
    assert "[INTENT][CREATED] symbol=ABCD price=None" in out
    assert "BLOCKED_BY_INVALID_INPUT" not in out
    assert "TRIGGER_WITHOUT_INTENT" not in out


def test_paper_mode_uses_scanner_fallback_after_ibkr_timeout(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 12.34}],
        },
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.resolve_entry_price",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PriceResolutionError("ABCD", "NO_IBKR_PRICE_AVAILABLE")),
    )
    monkeypatch.setattr("src.core_engine.orchestrator._wait_for_ibkr_snapshot_for_symbol", lambda **_: False)
    monkeypatch.setattr(
        "src.core_engine.orchestrator.build_trade_intents",
        lambda *args, **_kwargs: [
            TradeIntentRecord(
                symbol=args[1],
                intent_id="intent-ABCD",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price_source="SCANNER_LAST_PRICE",
            )
        ],
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.evaluate_trade_intents",
        lambda **_: [
            RiskDecisionRecord(
                symbol="ABCD",
                intent_id="intent-ABCD",
                decision="ALLOW",
                max_position_size=100,
                constraints=[],
                triggered_rules=[],
                rationale="PASS",
                approved_quantity=1,
            )
        ],
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.execute_intents",
        lambda **_: [ExecutionEvent(symbol="ABCD", intent_id="intent-ABCD", action="SUBMITTED", detail="ok", broker_order_id=1)],
    )

    run_cycle(cycle_id=1, mode_value="PAPER", forced_session_state=SessionState.PRE)
    out = capsys.readouterr().out
    assert "[INTENT][CREATED] symbol=ABCD price=None" in out
    assert "[EXECUTION][SUBMIT_RESULT] symbol=ABCD submitted=True" in out


def test_blocker_taxonomy_setup_but_no_trigger(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 12.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (12.0, "IBKR_SNAPSHOT"))
    monkeypatch.setattr(
        "src.strategies.ross_momentum.patterns.pattern_evaluator.PatternEvaluator.evaluate",
        lambda *_args, **_kwargs: _summary(detected=True, confidence=0.1, entry_zone=None),
    )
    monkeypatch.setattr("src.core_engine.orchestrator.build_trade_intents", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("src.core_engine.orchestrator.evaluate_trade_intents", lambda **_: [])
    monkeypatch.setattr("src.core_engine.orchestrator.execute_intents", lambda **_: [])

    run_cycle(cycle_id=11, mode_value="PAPER", forced_session_state=SessionState.PRE)
    out = capsys.readouterr().out
    assert "[TRADE_BLOCKER][ROW] {'symbol': 'ABCD', 'blocker_category': 'TRIGGER_NOT_CONFIRMED'" in out


def test_blocker_taxonomy_trigger_but_risk_blocked(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (5.0, "IBKR_SNAPSHOT"))
    monkeypatch.setattr(
        "src.core_engine.orchestrator.build_trade_intents",
        lambda *args, **_kwargs: [
            TradeIntentRecord(
                symbol=args[1],
                intent_id="intent-ABCD",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price_source="IBKR_SNAPSHOT",
            )
        ],
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.evaluate_trade_intents",
        lambda **_: [
            RiskDecisionRecord(
                symbol="ABCD",
                intent_id="intent-ABCD",
                decision="BLOCK",
                max_position_size=100,
                constraints=[],
                triggered_rules=["MAX_RISK"],
                rationale="risk fail",
                approved_quantity=0,
                block_reason="MAX_RISK",
            )
        ],
    )
    monkeypatch.setattr("src.core_engine.orchestrator.execute_intents", lambda **_: [])
    run_cycle(cycle_id=12, mode_value="PAPER", forced_session_state=SessionState.PRE)
    out = capsys.readouterr().out
    assert "[TRADE_BLOCKER][ROW] {'symbol': 'ABCD', 'blocker_category': 'RISK_BLOCKED'" in out


def test_admission_summary_reflects_success_path(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (5.0, "IBKR_SNAPSHOT"))
    monkeypatch.setattr(
        "src.core_engine.orchestrator.build_trade_intents",
        lambda *args, **_kwargs: [
            TradeIntentRecord(
                symbol=args[1],
                intent_id="intent-ABCD",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price_source="IBKR_SNAPSHOT",
            )
        ],
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.evaluate_trade_intents",
        lambda **_: [
            RiskDecisionRecord(
                symbol="ABCD",
                intent_id="intent-ABCD",
                decision="ALLOW",
                max_position_size=100,
                constraints=[],
                triggered_rules=[],
                rationale="PASS",
                approved_quantity=1,
            )
        ],
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.execute_intents",
        lambda **_: [ExecutionEvent(symbol="ABCD", intent_id="intent-ABCD", action="SUBMITTED", detail="ok", broker_order_id=99)],
    )
    run_cycle(cycle_id=13, mode_value="PAPER", forced_session_state=SessionState.PRE)
    out = capsys.readouterr().out
    assert "[TRADE_ADMISSION][SUMMARY]" in out
    assert "'execution_attempted_count': 1" in out


def test_completed_trade_emits_analytics_row(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (5.0, "IBKR_SNAPSHOT"))
    monkeypatch.setattr(
        "src.core_engine.orchestrator.build_trade_intents",
        lambda *args, **_kwargs: [
            TradeIntentRecord(
                symbol=args[1],
                intent_id="intent-ABCD",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price_source="IBKR_SNAPSHOT",
            )
        ],
    )
    monkeypatch.setattr(
        "src.core_engine.orchestrator.evaluate_trade_intents",
        lambda **_: [
            RiskDecisionRecord(
                symbol="ABCD",
                intent_id="intent-ABCD",
                decision="ALLOW",
                max_position_size=100,
                constraints=[],
                triggered_rules=[],
                rationale="PASS",
                approved_quantity=1,
            )
        ],
    )
    event = ExecutionEvent(
        symbol="ABCD",
        intent_id="intent-ABCD",
        action="SUBMITTED",
        detail="profit_target",
        broker_order_id=99,
        event_type="ORDER_FILLED",
        filled_quantity=10,
        remaining_quantity=0,
        avg_fill_price=5.01,
    )
    setattr(event, "client_order_id", "trade-1")
    monkeypatch.setattr("src.core_engine.orchestrator.execute_intents", lambda **_: [event])

    trade = SimpleNamespace(
        trade_id="trade-1",
        state="EXITED",
        avg_fill_price=5.0,
        exit_fill_price=5.25,
        exit_fill_time="2026-04-15T14:31:00+00:00",
        last_update_ts="2026-04-15T14:30:00+00:00",
        realized_pnl=2.5,
        holding_duration_seconds=60,
        exit_reason="TARGET_FILLED",
        partial_exit_count=0,
    )
    lifecycle = SimpleNamespace(
        get_trade=lambda trade_id: trade if trade_id == "trade-1" else None,
    )

    run_cycle(cycle_id=14, mode_value="PAPER", forced_session_state=SessionState.PRE, lifecycle_engine=lifecycle)
    out = capsys.readouterr().out
    assert "[TRADE_ANALYTICS][ROW]" in out
    assert "'realized_pnl': 2.5" in out
    assert "'trade_id': 'trade-1'" in out


def test_make_it_trade_cycle_summary_counts_consistent(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (5.0, "IBKR_SNAPSHOT"))
    monkeypatch.setattr("src.core_engine.orchestrator.build_trade_intents", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("src.core_engine.orchestrator.evaluate_trade_intents", lambda **_: [])
    monkeypatch.setattr("src.core_engine.orchestrator.execute_intents", lambda **_: [])
    run_cycle(cycle_id=15, mode_value="PAPER", forced_session_state=SessionState.PRE)
    out = capsys.readouterr().out
    summary_line = next(line for line in out.splitlines() if line.startswith("[MAKE_IT_TRADE][CYCLE_SUMMARY]"))
    payload = ast.literal_eval(summary_line.split(" ", 1)[1])
    assert payload["trigger_count"] <= payload["setup_count"]
    assert payload["intent_count"] <= payload["trigger_count"]
    assert payload["risk_pass_count"] <= payload["intent_count"]


def test_open_trade_not_in_analytics(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (5.0, "IBKR_SNAPSHOT"))
    monkeypatch.setattr("src.core_engine.orchestrator.build_trade_intents", lambda *args, **_kwargs: [
        TradeIntentRecord(symbol=args[1], intent_id="intent-ABCD", setup_id="GAP_GO", side="LONG", entry="breakout", stop="structure", rationale="test", entry_price_source="IBKR_SNAPSHOT")
    ])
    monkeypatch.setattr("src.core_engine.orchestrator.evaluate_trade_intents", lambda **_: [
        RiskDecisionRecord(symbol="ABCD", intent_id="intent-ABCD", decision="ALLOW", max_position_size=100, constraints=[], triggered_rules=[], rationale="PASS", approved_quantity=1)
    ])
    event = ExecutionEvent(symbol="ABCD", intent_id="intent-ABCD", action="SUBMITTED", detail="ok", broker_order_id=99, event_type="ORDER_FILLED", filled_quantity=10)
    setattr(event, "client_order_id", "trade-open")
    monkeypatch.setattr("src.core_engine.orchestrator.execute_intents", lambda **_: [event])

    trade = SimpleNamespace(state="PROTECTED", avg_fill_price=5.0)
    lifecycle = SimpleNamespace(get_trade=lambda trade_id: trade if trade_id == "trade-open" else None)
    run_cycle(cycle_id=16, mode_value="PAPER", forced_session_state=SessionState.PRE, lifecycle_engine=lifecycle)
    out = capsys.readouterr().out
    assert "[TRADE_ANALYTICS][ROW]" not in out


def test_partial_then_full_exit_correct_pnl(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (5.0, "IBKR_SNAPSHOT"))
    monkeypatch.setattr("src.core_engine.orchestrator.build_trade_intents", lambda *args, **_kwargs: [
        TradeIntentRecord(symbol=args[1], intent_id="intent-ABCD", setup_id="GAP_GO", side="LONG", entry="breakout", stop="structure", rationale="test", entry_price_source="IBKR_SNAPSHOT")
    ])
    monkeypatch.setattr("src.core_engine.orchestrator.evaluate_trade_intents", lambda **_: [
        RiskDecisionRecord(symbol="ABCD", intent_id="intent-ABCD", decision="ALLOW", max_position_size=100, constraints=[], triggered_rules=[], rationale="PASS", approved_quantity=1)
    ])
    event = ExecutionEvent(symbol="ABCD", intent_id="intent-ABCD", action="SUBMITTED", detail="ok", broker_order_id=99, event_type="ORDER_FILLED", filled_quantity=10)
    setattr(event, "client_order_id", "trade-partial")
    monkeypatch.setattr("src.core_engine.orchestrator.execute_intents", lambda **_: [event])

    trade = SimpleNamespace(
        state="EXITED",
        avg_fill_price=10.0,
        exit_fill_price=10.5,
        exit_fill_time="2026-04-15T14:31:00+00:00",
        last_update_ts="2026-04-15T14:30:00+00:00",
        realized_pnl=14.0,
        holding_duration_seconds=60,
        exit_reason="TARGET_FILLED",
        partial_exit_count=1,
    )
    lifecycle = SimpleNamespace(get_trade=lambda trade_id: trade if trade_id == "trade-partial" else None)
    run_cycle(cycle_id=17, mode_value="PAPER", forced_session_state=SessionState.PRE, lifecycle_engine=lifecycle)
    out = capsys.readouterr().out
    assert "'realized_pnl': 14.0" in out
    assert "'partial_exit_count': 1" in out


def test_expectancy_calculation() -> None:
    from src.core_engine.orchestrator import _compute_expectancy_metrics

    rows = [
        {"realized_pnl": 100.0},
        {"realized_pnl": -50.0},
        {"realized_pnl": 25.0},
        {"realized_pnl": -25.0},
    ]
    metrics = _compute_expectancy_metrics(rows)
    assert metrics["win_rate"] == 0.5
    assert metrics["avg_winner"] == 62.5
    assert metrics["avg_loser"] == -37.5
    assert metrics["expectancy"] == 12.5


def test_analytics_uses_lifecycle_truth(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "src.core_engine.orchestrator.run_scanner_cycle",
        lambda **_: {
            "watchlist_k_symbols": ["ABCD"],
            "focus_m_symbols": ["ABCD"],
            "data_quality_by_symbol": {},
            "watchlist_k": [{"symbol": "ABCD", "last_price": 5.0}],
        },
    )
    monkeypatch.setattr("src.core_engine.orchestrator.resolve_entry_price", lambda *_args, **_kwargs: (5.0, "IBKR_SNAPSHOT"))
    monkeypatch.setattr("src.core_engine.orchestrator.build_trade_intents", lambda *args, **_kwargs: [
        TradeIntentRecord(symbol=args[1], intent_id="intent-ABCD", setup_id="GAP_GO", side="LONG", entry="breakout", stop="structure", rationale="test", entry_price_source="IBKR_SNAPSHOT")
    ])
    monkeypatch.setattr("src.core_engine.orchestrator.evaluate_trade_intents", lambda **_: [
        RiskDecisionRecord(symbol="ABCD", intent_id="intent-ABCD", decision="ALLOW", max_position_size=100, constraints=[], triggered_rules=[], rationale="PASS", approved_quantity=1)
    ])
    event = ExecutionEvent(symbol="ABCD", intent_id="intent-ABCD", action="SUBMITTED", detail="ok", broker_order_id=99, event_type="ORDER_FILLED", filled_quantity=10)
    setattr(event, "client_order_id", "trade-real")
    monkeypatch.setattr("src.core_engine.orchestrator.execute_intents", lambda **_: [event])

    trade = SimpleNamespace(
        state="EXITED",
        avg_fill_price=10.0,
        exit_fill_price=11.0,
        exit_fill_time="2026-04-15T14:31:00+00:00",
        last_update_ts="2026-04-15T14:30:00+00:00",
        realized_pnl=10.0,
        holding_duration_seconds=60,
        exit_reason="TARGET_FILLED",
        partial_exit_count=0,
    )
    lifecycle = SimpleNamespace(get_trade=lambda trade_id: trade if trade_id == "trade-real" else None)

    run_cycle(cycle_id=18, mode_value="PAPER", forced_session_state=SessionState.PRE, lifecycle_engine=lifecycle)
    out = capsys.readouterr().out
    assert "'realized_pnl': 10.0" in out
    assert "'exit_price': 11.0" in out
