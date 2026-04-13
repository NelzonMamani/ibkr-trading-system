from __future__ import annotations

from dataclasses import dataclass

from src.execution.dev_tools.flatten_positions import force_flatten_all_positions


@dataclass(frozen=True)
class FlattenResult:
    remaining: int
    status: str
    positions_detected: int
    close_orders_submitted: int


def flatten_all_positions(ibkr_client, timeout_seconds: int = 30) -> FlattenResult:
    payload = force_flatten_all_positions(ibkr_client, timeout_seconds=timeout_seconds)
    return FlattenResult(
        remaining=int(payload.get("positions_remaining", 0) or 0),
        status=str(payload.get("status", "FAILED") or "FAILED"),
        positions_detected=int(payload.get("positions_detected", 0) or 0),
        close_orders_submitted=int(payload.get("close_orders_submitted", 0) or 0),
    )
