from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.config.config_resolver import set_config_overrides
from src.core.time.trading_windows import (
    build_trading_window_policy,
    resolve_trading_window_decision,
)
from src.execution.execution_engine import ExecutionEngine
from src.models.data_models import TradeIntent
from src.risk.risk_engine import RiskEngine


def test_tha_allows_real_execution_flow() -> None:
    now = datetime.now(timezone.utc)
    day = now.astimezone().strftime("%Y%m%d")
    later = (now + timedelta(hours=1)).astimezone()
    start_hhmm = now.astimezone().strftime("%H%M")
    end_hhmm = later.strftime("%H%M")
    if end_hhmm == start_hhmm:
        end_hhmm = "2359"
    trading_hours = f"{day}:{start_hhmm}-{end_hhmm}"

    policy = build_trading_window_policy(
        symbol="THA",
        now=now,
        run_mode="PAPER",
        trading_hours=trading_hours,
        liquid_hours=None,
        timezone=str(now.astimezone().tzinfo),
    )
    tha_decision = resolve_trading_window_decision(policy=policy, now=now)
    assert tha_decision.in_window is True
    assert tha_decision.allow_entries is True

    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        intent = TradeIntent(
            symbol="THA",
            direction="LONG",
            strategy_name="ross_momentum",
            confidence=0.91,
            rationale="test-tha-inside-window",
            trader_type="AUTO",
        )
        intent.decision_id = "tha-flow-1"
        intent.trigger_ready = True
        intent.entry_price = 10.0
        intent.stop_loss_price = 9.8
        intent.quantity = 10
        intent.tha_in_window = True

        risk_decision = RiskEngine().evaluate_trade_intent(intent)
        assert risk_decision.allowed is True
        assert bool(risk_decision.rationale)

        execution_engine = ExecutionEngine()
        execution_engine.current_tick = 1
        execution_result = execution_engine.execute_trade(risk_decision)

        assert bool(getattr(execution_result, "attempted", False)) is True
        assert str(getattr(execution_result, "status", "")).upper() not in {"BLOCKED", "REJECTED"}
    finally:
        set_config_overrides(None)
