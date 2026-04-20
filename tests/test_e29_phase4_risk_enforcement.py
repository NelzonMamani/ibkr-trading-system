from __future__ import annotations

from dataclasses import dataclass

from src.config.config_resolver import set_config_overrides
from src.models.data_models import TradeIntent
from src.risk.risk_engine import PortfolioStateDesyncError, RiskEngine


@dataclass
class _Signals:
    max_drawdown_breached: bool = False
    pnl_drop_rate_exceeded: bool = False
    too_many_open_positions: bool = False
    drift_detected: bool = False


@dataclass
class _PortfolioState:
    total_exposure: float = 0.0
    total_open_positions: int = 0


class _LifecycleStub:
    def __init__(self, signals: _Signals, state: _PortfolioState, findings: list[dict] | None = None):
        self._signals = signals
        self._state = state
        self._findings = findings or []

    def compute_lifecycle_risk_signals(self):
        return self._signals

    def build_portfolio_state(self):
        return self._state

    def get_drift_report(self):
        return self._findings


def _intent() -> TradeIntent:
    intent = TradeIntent(
        symbol="AAPL",
        direction="LONG",
        strategy_name="ross_momentum",
        confidence=0.9,
        rationale="test",
        trader_type="SYSTEM",
        decision_id="decision-1",
        stop_loss_price=9.5,
    )
    intent.entry_price = 10.0
    intent.quantity = 100
    return intent


def test_kill_switch_triggers_on_drawdown_and_blocks_all_trades() -> None:
    set_config_overrides({"RUN_MODE": "SIM", "EXECUTION_ENABLED": True})
    try:
        engine = RiskEngine()
        engine.set_trade_lifecycle_engine(
            _LifecycleStub(
                signals=_Signals(max_drawdown_breached=True),
                state=_PortfolioState(total_exposure=100.0, total_open_positions=1),
            )
        )
        first = engine.evaluate_trade_intent(_intent())
        assert first.allowed is False
        assert first.blocked_by_lifecycle is True
        assert engine.kill_switch.active is True
        assert engine.kill_switch.reason == "drawdown"

        engine.set_trade_lifecycle_engine(
            _LifecycleStub(
                signals=_Signals(),
                state=_PortfolioState(total_exposure=50.0, total_open_positions=1),
            )
        )
        second = engine.evaluate_trade_intent(_intent())
        assert second.allowed is False
        assert second.lifecycle_block_reason == "LIFECYCLE_KILL_SWITCH_ACTIVE"
    finally:
        set_config_overrides(None)


def test_capital_limits_block_portfolio_and_position_exposure() -> None:
    set_config_overrides(
        {
            "RUN_MODE": "SIM",
            "EXECUTION_ENABLED": True,
            "LIFECYCLE_MAX_PORTFOLIO_EXPOSURE": 1000.0,
            "LIFECYCLE_MAX_POSITION_EXPOSURE": 800.0,
            "LIFECYCLE_MAX_POSITIONS": 5,
        }
    )
    try:
        engine = RiskEngine()
        engine.set_trade_lifecycle_engine(
            _LifecycleStub(
                signals=_Signals(),
                state=_PortfolioState(total_exposure=950.0, total_open_positions=1),
            )
        )
        decision = engine.evaluate_trade_intent(_intent())
        assert decision.allowed is False
        assert decision.lifecycle_block_reason == "CAPITAL_PORTFOLIO_LIMIT"

        intent = _intent()
        intent.quantity = 90
        engine.set_trade_lifecycle_engine(
            _LifecycleStub(
                signals=_Signals(),
                state=_PortfolioState(total_exposure=100.0, total_open_positions=1),
            )
        )
        position_block = engine.evaluate_trade_intent(intent)
        assert position_block.allowed is False
        assert position_block.lifecycle_block_reason == "CAPITAL_POSITION_LIMIT"
    finally:
        set_config_overrides(None)


def test_critical_broker_drift_activates_kill_switch_and_blocks() -> None:
    set_config_overrides({"RUN_MODE": "SIM", "EXECUTION_ENABLED": True})
    try:
        engine = RiskEngine()
        engine.set_trade_lifecycle_engine(
            _LifecycleStub(
                signals=_Signals(drift_detected=True),
                state=_PortfolioState(total_exposure=100.0, total_open_positions=1),
                findings=[{"severity": "CRITICAL", "status": "ORPHANED"}],
            )
        )
        decision = engine.evaluate_trade_intent(_intent())
        assert decision.allowed is False
        assert engine.kill_switch.active is True
        assert decision.lifecycle_block_reason == "LIFECYCLE_KILL_SWITCH_ACTIVE"
    finally:
        set_config_overrides(None)


class _FailingLifecycle:
    def compute_lifecycle_risk_signals(self):
        raise RuntimeError("boom")

    def build_portfolio_state(self):
        raise RuntimeError("boom")

    def get_drift_report(self):
        raise RuntimeError("boom")


def test_lifecycle_bridge_failure_is_non_blocking() -> None:
    set_config_overrides({"RUN_MODE": "SIM", "EXECUTION_ENABLED": True})
    try:
        engine = RiskEngine()
        engine.set_trade_lifecycle_engine(_FailingLifecycle())
        decision = engine.evaluate_trade_intent(_intent())
        assert decision is not None
        assert decision.blocked_by_lifecycle is False
    finally:
        set_config_overrides(None)


def test_portfolio_state_desync_invariant_raises() -> None:
    set_config_overrides({"RUN_MODE": "SIM", "EXECUTION_ENABLED": True})
    try:
        engine = RiskEngine()
        engine.set_trade_lifecycle_engine(
            _LifecycleStub(
                signals=_Signals(),
                state=_PortfolioState(total_exposure=0.0, total_open_positions=1),
            )
        )
        try:
            engine.evaluate_trade_intent(_intent())
            assert False, "expected desync invariant failure"
        except PortfolioStateDesyncError:
            pass
    finally:
        set_config_overrides(None)
