from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from core.orchestrator import CoreOrchestrator  # noqa: E402
from models.data_models import TradeIntent  # noqa: E402


def test_market_data_validation_teaching_is_na(monkeypatch):
    monkeypatch.delenv("SCANNER_MODE", raising=False)
    monkeypatch.setenv("RUN_MODE", "SIM")
    orchestrator = CoreOrchestrator()

    status, ok = orchestrator._resolve_market_data_status()

    assert status == "N/A"
    assert ok is True


def test_dedup_normalisation_drops_duplicates(monkeypatch):
    monkeypatch.setenv("RUN_MODE", "SIM")
    monkeypatch.setenv("INTENT_DEDUP_SELFTEST_ENABLED", "false")
    orchestrator = CoreOrchestrator()

    intents = [
        TradeIntent(
            symbol="AAPL",
            direction="LONG",
            strategy_name="TEST",
            confidence=0.4,
            rationale="first",
            trader_type="MOMENTUM",
        ),
        TradeIntent(
            symbol="AAPL",
            direction="LONG",
            strategy_name="TEST",
            confidence=0.7,
            rationale="second",
            trader_type="MOMENTUM",
        ),
    ]

    normalized = orchestrator._normalize_trade_intents(intents)

    assert len(normalized) == 1
    assert normalized[0].confidence == 0.7
