from __future__ import annotations

from types import SimpleNamespace

from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def _summary(*, session: str, pct_change: float, rvol: float, volume: float, spread: float = 0.02):
    return SimpleNamespace(
        session_context=session,
        quality_flags=[],
        volume=volume,
        rvol=rvol,
        spread=spread,
        pct_change=pct_change,
        last_price=8.0,
        has_levels=True,
    )


def _inputs():
    return SimpleNamespace(candles=[1, 2, 3])


def test_phase_aware_thresholds_are_stricter_midday_than_pre() -> None:
    strategy = RossMomentumStrategyV1()
    pre_summary = _summary(session="PRE", pct_change=4.2, rvol=1.0, volume=20_000)
    rth_mid_summary = _summary(session="RTH_MID", pct_change=4.2, rvol=1.0, volume=20_000)

    pre_reasons = strategy._data_contract_block_reasons(
        symbol="PRET",
        input_summary=pre_summary,
        inputs=_inputs(),
        session_phase="PRE",
    )
    rth_mid_reasons = strategy._data_contract_block_reasons(
        symbol="MIDT",
        input_summary=rth_mid_summary,
        inputs=_inputs(),
        session_phase="RTH_MID",
    )

    assert "PCT_CHANGE_BELOW_THRESHOLD(4.0)" not in pre_reasons
    assert any(reason.startswith("PCT_CHANGE_BELOW_THRESHOLD") for reason in rth_mid_reasons)


def test_strong_momentum_contract_is_phase_aware() -> None:
    strategy = RossMomentumStrategyV1()
    candidate = _summary(session="PRE", pct_change=5.5, rvol=1.5, volume=30_000)

    assert strategy._is_strong_momentum(candidate, session_phase="PRE", allow_ah=False) is True
    assert strategy._is_strong_momentum(candidate, session_phase="AH", allow_ah=False) is False
