from __future__ import annotations

from src.config.runtime_config import RunMode
from src.strategy.strategy_runner import StrategyRunner
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


class _CaptureRunner:
    def __init__(self) -> None:
        self.payload = None

    def run(self, context):
        self.payload = dict(context)
        return {"trade_intents": [], "trade_ready_count": 0, "reports": []}


def test_strategy_runner_passes_session_contract_to_ross_runner() -> None:
    strategy = RossMomentumStrategyV1()
    runner = StrategyRunner(strategies=[strategy])
    capture = _CaptureRunner()
    runner._runner_registry[strategy.name] = capture

    session_contract = {
        "canonical_session": "PRE",
        "detected_session": "PREMARKET",
        "session_decision_source": "unit_test",
    }
    runner.process(
        strategy_key="ross_momentum",
        watchlist=[{"symbol": "TST"}],
        snapshots={},
        session_label="PRE",
        timestamp_utc="cycle-1",
        mode=RunMode.SIM,
        session_phase="PRE",
        session_contract=session_contract,
    )

    assert capture.payload is not None
    assert capture.payload["session_contract"] == session_contract
