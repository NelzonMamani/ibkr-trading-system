from __future__ import annotations

import pytest

from src.core.pricing.price_resolver import PriceResolutionError, resolve_entry_price


def test_resolve_entry_price_scanner_only_context_fails_no_valid_price_source() -> None:
    context = {
        "scanner_payload": {
            "focus_m": [{"symbol": "AAPL", "last_price": 123.45}],
        }
    }

    with pytest.raises(PriceResolutionError, match="NO_VALID_PRICE_SOURCE"):
        resolve_entry_price("AAPL", context)
