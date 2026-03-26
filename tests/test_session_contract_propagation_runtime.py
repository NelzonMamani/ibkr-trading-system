from __future__ import annotations

from src.scanner.session_contract import build_canonical_session_contract
from src.strategy.strategy_runner import StrategyRunner


def test_build_canonical_session_contract_pre_fields() -> None:
    contract = build_canonical_session_contract(
        detected_session="PRE",
        session_decision_source="MARKET_CLOCK",
    )
    assert contract.raw_detected_session == "PRE"
    assert contract.canonical_session == "PRE"
    assert contract.execution_window_allowed is True
    assert contract.pct_reference_price_type == "LAST_COMPLETED_RTH_CLOSE"
    assert contract.gap_reference_type == "SESSION_OPEN_VS_LAST_COMPLETED_RTH_CLOSE"


def test_strategy_runner_passes_session_contract_to_runner(monkeypatch) -> None:
    runner = StrategyRunner()
    captured: dict[str, object] = {}

    class _FakeRunner:
        def run(self, context):
            captured.update(context)
            return {"trade_intents": [], "trade_ready_count": 0}

    first_name = runner.strategies[0].name
    runner._runner_registry[first_name] = _FakeRunner()
    runner.process(
        strategy_key="ross_momentum",
        watchlist=[{"symbol": "AAPL"}],
        snapshots={},
        session_label="RTH_MID",
        timestamp_utc="2026-03-26T12:00:00+00:00",
        mode=type("M", (), {"value": "PAPER"})(),
        session_phase="RTH_MID",
    )
    assert "session_contract" in captured
    payload = captured["session_contract"]
    assert isinstance(payload, dict)
    assert payload["canonical_session"] == "RTH_MID"
