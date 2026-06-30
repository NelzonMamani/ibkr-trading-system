"""Runner wrapper for Ross Momentum strategy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


_FOCUS_KEYS = ("focus_list", "focus_symbols", "focus_m_symbols")


def _row_symbol(row: Any) -> str | None:
    if isinstance(row, str):
        symbol = row
    elif isinstance(row, dict):
        symbol = row.get("symbol")
    else:
        symbol = getattr(row, "symbol", None)
    normalized = str(symbol or "").strip().upper()
    return normalized or None


def _read_focus_value(row: Any, key: str) -> tuple[bool, Any]:
    if isinstance(row, dict):
        return key in row, row.get(key)
    if hasattr(row, key):
        return True, getattr(row, key)
    return False, None


def _focus_symbols_from(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        symbol = value.strip().upper()
        return {symbol} if symbol else set()
    if isinstance(value, Sequence):
        symbols = {_row_symbol(item) for item in value}
        return {symbol for symbol in symbols if symbol}
    symbol = _row_symbol(value)
    return {symbol} if symbol else set()


def _filter_watchlist_for_explicit_focus(watchlist: Sequence[object]) -> list[object]:
    rows = list(watchlist or [])
    explicit_focus_seen = False
    allowed_symbols: set[str] = set()
    for row in rows:
        for key in _FOCUS_KEYS:
            has_value, value = _read_focus_value(row, key)
            if not has_value:
                continue
            explicit_focus_seen = True
            allowed_symbols.update(_focus_symbols_from(value))

    if not explicit_focus_seen:
        return rows

    filtered: list[object] = []
    for row in rows:
        symbol = _row_symbol(row)
        if symbol and symbol in allowed_symbols:
            filtered.append(row)
            continue
        print(
            "[ROSS][FOCUS][SKIP] "
            f"symbol={symbol or 'UNKNOWN'} reason=NOT_IN_FOCUS_LIST execution_ineligible=true"
        )
    return filtered


class RossMomentumRunner:
    def __init__(self) -> None:
        self.strategy = RossMomentumStrategyV1()

    def run(self, context):
        watchlist = _filter_watchlist_for_explicit_focus(context.get("watchlist", []))
        intents = self.strategy.process_watchlist(
            watchlist=watchlist,
            snapshots=context.get("snapshots", {}),
            session_label=context.get("session_label"),
            timestamp_utc=context.get("timestamp_utc"),
            mode=context.get("mode"),
            session_phase=context.get("session_phase"),
        )
        trade_ready_count = sum(
            1
            for intent in intents
            if str(getattr(intent, "decision", "TRADE_READY")).upper() == "TRADE_READY"
        )
        return {
            "trade_intents": intents,
            "trade_ready_count": trade_ready_count,
            "reports": [],
        }
