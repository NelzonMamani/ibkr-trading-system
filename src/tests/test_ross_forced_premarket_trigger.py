from types import SimpleNamespace

from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def _summary(*, session: str, pct_change: float | None, spread: float | None, last: float | None, volume: float | None):
    return SimpleNamespace(
        session_context=session,
        pct_change=pct_change,
        spread=spread,
        last_price=last,
        volume=volume,
    )


def test_forced_premarket_trigger_injected_when_debug_flag_enabled():
    strategy = RossMomentumStrategyV1()
    strategy._force_premarket_trigger = True
    candidates: list[dict] = []

    strategy._inject_forced_premarket_trigger(
        symbol="ABCD",
        input_summary=_summary(session="PRE", pct_change=7.2, spread=0.03, last=5.5, volume=120000),
        trigger_candidates=candidates,
    )

    assert len(candidates) == 1
    assert candidates[0]["trigger_type"] == "DEBUG_PREMARKET_BREAK"
    assert candidates[0]["trigger_ready_now"] is True
    assert candidates[0]["setup_family_id"] == "PREMARKET_HIGH_BREAK"


def test_forced_premarket_trigger_not_injected_without_debug_flag():
    strategy = RossMomentumStrategyV1()
    strategy._force_premarket_trigger = False
    candidates: list[dict] = []

    strategy._inject_forced_premarket_trigger(
        symbol="ABCD",
        input_summary=_summary(session="PRE", pct_change=8.0, spread=0.02, last=6.1, volume=90000),
        trigger_candidates=candidates,
    )

    assert candidates == []


def test_forced_premarket_trigger_respects_minimums():
    strategy = RossMomentumStrategyV1()
    strategy._force_premarket_trigger = True
    candidates: list[dict] = []

    strategy._inject_forced_premarket_trigger(
        symbol="ABCD",
        input_summary=_summary(session="PRE", pct_change=4.5, spread=0.02, last=6.1, volume=90000),
        trigger_candidates=candidates,
    )

    assert candidates == []
