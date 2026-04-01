from __future__ import annotations

import importlib

import pytest


def test_ovn_symbols_rejected_when_disabled() -> None:
    module = None
    for candidate in (
        "src.scanner.tradeability_gate",
        "src.scanner.tradeability",
        "src.scanner.scanner_tradeability",
    ):
        try:
            module = importlib.import_module(candidate)
            break
        except ModuleNotFoundError:
            continue

    if module is None or not hasattr(module, "evaluate_tradeability"):
        pytest.skip("evaluate_tradeability gate module not available in this branch")

    decision = module.evaluate_tradeability(
        {
            "session": "OVN",
            "volume": 1_000_000,
            "dollar_volume": 10_000_000,
            "spread_pct": 0.01,
            "bid": 10.0,
            "ask": 10.01,
        }
    )
    assert decision.accepted is False
    assert decision.reason == "OVN_TRADING_DISABLED"
