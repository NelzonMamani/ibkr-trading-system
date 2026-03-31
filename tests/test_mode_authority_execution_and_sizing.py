from __future__ import annotations

from src.config.config_resolver import set_config_overrides
from src.core.intent import build_execution_intent
from src.core.mode_authority import resolve_mode_authority
from src.core_engine.events import TradeIntentRecord
from src.core_engine.orchestrator import _enforce_canonical_price_authority, run_cycle
from src.core_engine.state import RunMode, SessionState
from src.risk.risk_audit import INITIAL_POSITION_PCT, AccountSnapshot, evaluate_trade_intents
from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec


def test_mode_authority_paper_execution_enabled_is_executable() -> None:
    authority = resolve_mode_authority("PAPER", True)
    assert authority.effective_mode == "PAPER"
    assert authority.trade_enabled is True
    assert authority.scan_only is False


def test_mode_authority_paper_execution_disabled_is_observational() -> None:
    authority = resolve_mode_authority("PAPER", False)
    assert authority.effective_mode == "PAPER"
    assert authority.trade_enabled is False
    assert authority.scan_only is True


def test_mode_authority_read_only_stays_scan_only() -> None:
    authority = resolve_mode_authority("READ_ONLY", True)
    assert authority.effective_mode == "READ_ONLY"
    assert authority.trade_enabled is False
    assert authority.scan_only is True


def test_mode_authority_live_execution_disabled_is_observational() -> None:
    authority = resolve_mode_authority("LIVE", False)
    assert authority.effective_mode == "LIVE"
    assert authority.trade_enabled is False
    assert authority.scan_only is True


def test_mode_authority_env_paper_not_downgraded(monkeypatch) -> None:
    monkeypatch.setenv("RUN_MODE", "PAPER")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    authority = resolve_mode_authority("READ_ONLY", True)
    assert authority.requested_mode == "PAPER"
    assert authority.effective_mode == "PAPER"
    assert authority.trade_enabled is True
    assert authority.scan_only is False


def test_execution_intent_uses_mode_authority_scan_only_semantics() -> None:
    policy = StockSelectionSpec()
    intent = build_execution_intent(
        strategy_name="ROSS_MOMENTUM",
        mode="PAPER",
        session_phase="PRE",
        policy=policy,
        execution_enabled=False,
    )
    assert intent.mode == "PAPER"
    assert intent.trade_enabled is False
    assert intent.scan_only is True


def test_risk_sizing_uses_price_derived_quantity() -> None:
    available_capital = 20_000.0
    focus_count = 1
    entry_price = 25.0
    decisions = evaluate_trade_intents(
        intents=[
            TradeIntentRecord(
                symbol="SANE",
                intent_id="SANE-1",
                setup_id="GAP_GO",
                side="LONG",
                entry="breakout",
                stop="structure",
                rationale="test",
                entry_price=entry_price,
            )
        ],
        mode=RunMode.PAPER,
        health_status=None,
        account=AccountSnapshot(
            available_funds=available_capital,
            source="PAPER",
            canonical=True,
            broker_connection_state="SIMULATED",
        ),
    )
    capital_per_symbol = available_capital / focus_count
    initial_capital = capital_per_symbol * INITIAL_POSITION_PCT
    expected_quantity = int(initial_capital // entry_price)
    assert decisions[0].approved_quantity == expected_quantity
    assert decisions[0].approved_quantity != int(available_capital // entry_price)


def test_executable_paper_cycle_does_not_skip_scan_only_and_no_readonly_rule(capsys) -> None:
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "RUN_MODE_EFFECTIVE": "PAPER",
            "EXECUTION_ENABLED": True,
            "EXECUTION_ENABLED_EFFECTIVE": True,
            "SCANNER_DATA_SOURCE": "MOCK",
        }
    )
    try:
        run_cycle(cycle_id=1, mode_value="PAPER", forced_session_state=SessionState.PRE)
    finally:
        set_config_overrides(None)
    out = capsys.readouterr().out
    assert "[EXECUTION] Execution stage skipped — intent scan_only." not in out
    assert "MODE_READONLY" not in out
    assert "[PIPELINE][EXECUTION_GATE]" in out


def test_price_authority_allows_scanner_price_for_paper_after_hours() -> None:
    allowed, reason = _enforce_canonical_price_authority(
        symbol="AAPL",
        mode=RunMode.PAPER,
        session="AFTER",
        entry_price=100.0,
        entry_price_source="SCANNER_LAST_PRICE",
        scanner_payload={},
    )
    assert allowed is True
    assert reason == "PAPER_FALLBACK_ALLOWED"


def test_price_authority_blocks_scanner_price_for_paper_rth() -> None:
    allowed, reason = _enforce_canonical_price_authority(
        symbol="AAPL",
        mode=RunMode.PAPER,
        session="REG",
        entry_price=100.0,
        entry_price_source="SCANNER_LAST_PRICE",
        scanner_payload={},
    )
    assert allowed is False
    assert reason == "NON_CANONICAL_PRICE_SOURCE:SCANNER_LAST_PRICE"


def test_after_hours_preserves_paper_mode_for_lifecycle_validation(capsys) -> None:
    set_config_overrides(
        {
            "RUN_MODE": "PAPER",
            "RUN_MODE_EFFECTIVE": "PAPER",
            "EXECUTION_ENABLED": False,
            "EXECUTION_ENABLED_EFFECTIVE": False,
            "SCANNER_DATA_SOURCE": "MOCK",
        }
    )
    try:
        run_cycle(cycle_id=1, mode_value="PAPER", forced_session_state=SessionState.AFTER)
    finally:
        set_config_overrides(None)
    out = capsys.readouterr().out
    assert "[MODE][OVERRIDE] preserving PAPER mode during AFTER_HOURS for lifecycle validation" in out
    assert "[MODE][EXECUTION_CONTEXT]" in out
    assert "effective_mode=PAPER trade_enabled=True scan_only=False" in out
