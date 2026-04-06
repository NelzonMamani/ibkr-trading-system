from __future__ import annotations

from src.core_engine.events import ExecutionEvent, RiskDecisionRecord, TradeIntentRecord
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
        "src.core_engine.orchestrator.evaluate_trade_intents",
        lambda **_: [
            RiskDecisionRecord(
                symbol="ABCD",
                intent_id="RossMomentumStrategy:ABCD:Gap_Go",
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
                intent_id="RossMomentumStrategy:ABCD:Gap_Go",
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
    assert "[PRICE][AUTHORITY_VIOLATION] symbol=BAD mode=PAPER source=SCANNER_LAST_PRICE action=BLOCK" in out
    assert "[PIPELINE][INTENT] symbol=BAD created=false reason=BLOCKED_BY_PRICE_AUTHORITY" in out
    assert "[EXECUTION][SUBMIT_RESULT] symbol=GOOD submitted=True" in out
    assert "[CYCLE][PRICE_AUTHORITY_SUMMARY]" in out
