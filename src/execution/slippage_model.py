from __future__ import annotations

from typing import Dict, Tuple


class SlippageModel:
    """
    Deterministic, replay-safe slippage model.

    Applies a fixed per-share slippage based on trader_type and direction.
    Quantity sign is used to infer entry vs. exit for LONG trades so exits
    reverse the sign of the LONG slippage while SHORT slippage remains
    symmetric as specified.
    """

    _SLIPPAGE_TABLE: Dict[Tuple[str, str], float] = {
        ("SCALPER", "LONG"): 0.01,
        ("SCALPER", "SHORT"): -0.01,
        ("MOMENTUM", "LONG"): 0.02,
        ("MOMENTUM", "SHORT"): -0.02,
    }

    @staticmethod
    def apply_slippage(price: float, direction: str, trader_type: str, quantity: int) -> float:
        normalized_direction = (direction or "").upper()
        normalized_trader_type = (trader_type or "").upper()
        base_slippage = SlippageModel._SLIPPAGE_TABLE.get(
            (normalized_trader_type, normalized_direction), 0.0
        )

        is_exit = quantity < 0
        if is_exit and normalized_direction == "LONG":
            applied_slippage = -base_slippage
        else:
            applied_slippage = base_slippage

        adjusted_price = round(price + applied_slippage, 2)
        return adjusted_price
