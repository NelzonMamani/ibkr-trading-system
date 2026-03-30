from src.strategies.ross_momentum.patterns.pattern_trace import RossSymbolTrace
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def _trace(symbol: str, *, final_outcome: str, final_reason_code: str = "", pre_failure: str = "") -> RossSymbolTrace:
    return RossSymbolTrace(
        symbol=symbol,
        cycle_id="cycle-1",
        strategy_key="ross_momentum",
        session_label="PRE",
        session_phase="PRE",
        runtime_mode="SIM",
        symbol_source="watchlist",
        final_outcome=final_outcome,
        final_reason_code=final_reason_code,
        pre_registry_failure_reason=pre_failure,
    )


def test_cycle_summary_and_shutdown_summary_are_emitted(capsys) -> None:
    strategy = RossMomentumStrategyV1()
    traces = [
        _trace("INP", final_outcome="NO_SETUP:failed_to_build_inputs", pre_failure="failed_to_build_inputs"),
        _trace("SET", final_outcome="NO_SETUP:no_valid_pattern", final_reason_code="NO_VALID_PATTERN"),
        _trace("FIL", final_outcome="SETUP_FOUND_DECISION_REJECTED", final_reason_code="DECISION_REJECTED"),
        _trace("TRI", final_outcome="SETUP_FOUND_BUT_NO_TRIGGER", final_reason_code="TRIGGER_NOT_READY"),
        _trace("OK", final_outcome="SETUP_DETECTED_AND_TRANSLATED", final_reason_code="INTENT_GENERATED"),
    ]

    cycle_summary = strategy._build_ross_cycle_summary(symbol_traces=traces, intents_generated=1)
    strategy._update_ross_session_stats(cycle_summary)
    strategy._last_cycle_summary = cycle_summary
    strategy._print_ross_cycle_summary(cycle_summary)
    strategy.emit_shutdown_summary()

    out = capsys.readouterr().out
    assert "[ROSS][CYCLE_SUMMARY] symbols=5 intents=1" in out
    assert "fails(structure=0, setup=1, trigger=1, filter=1, input=1)" in out
    assert "dominant=setup" in out
    assert "[SYSTEM] Shutdown requested — generating summary..." in out
    assert "[ROSS][FINAL_SESSION_SUMMARY] cycles=1 symbols=5 intents=1" in out
    assert "[ROSS][FAILURE_DISTRIBUTION]" in out
    assert "[ROSS][LAST_CYCLE]" in out
