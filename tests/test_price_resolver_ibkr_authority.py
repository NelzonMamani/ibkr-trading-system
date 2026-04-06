from __future__ import annotations

import pytest

from src.core.pricing.price_resolver import PriceResolutionError, resolve_entry_price


def test_paper_uses_ibkr_snapshot_last_when_available() -> None:
    price, source = resolve_entry_price(
        "AAPL",
        {
            "run_mode": "PAPER",
            "ibkr_snapshot_by_symbol": {
                "AAPL": {"last_price": 101.25, "bid": 101.2, "ask": 101.3}
            },
            "scanner_payload": {"watchlist_k": [{"symbol": "AAPL", "last_price": 99.0}]},
        },
    )

    assert price == 101.25
    assert source == "IBKR_SNAPSHOT"


def test_paper_uses_ibkr_midpoint_when_last_missing() -> None:
    price, source = resolve_entry_price(
        "AAPL",
        {
            "run_mode": "PAPER",
            "ibkr_snapshot_by_symbol": {
                "AAPL": {"last_price": None, "bid": 100.0, "ask": 101.0}
            },
            "scanner_payload": {"watchlist_k": [{"symbol": "AAPL", "last_price": 99.0}]},
        },
    )

    assert price == 100.5
    assert source == "IBKR_SNAPSHOT_MID"


def test_paper_blocks_when_ibkr_missing_even_if_scanner_present() -> None:
    with pytest.raises(PriceResolutionError, match="NO_VALID_PRICE_SOURCE"):
        resolve_entry_price(
            "AAPL",
            {
                "run_mode": "PAPER",
                "ibkr_snapshot_by_symbol": {"AAPL": {"last_price": None, "bid": None, "ask": None}},
                "scanner_payload": {"watchlist_k": [{"symbol": "AAPL", "last_price": 99.0}]},
            },
        )


def test_sim_still_allows_scanner_fallback() -> None:
    price, source = resolve_entry_price(
        "AAPL",
        {
            "run_mode": "SIM",
            "scanner_payload": {"watchlist_k": [{"symbol": "AAPL", "last_price": 99.0}]},
        },
    )

    assert price == 99.0
    assert source == "SCANNER_LAST_PRICE"
