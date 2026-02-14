"""
Strategy Runner for Long Horizon Value.
Orchestrator calls this runner; it emits TradeIntents only.
"""

from __future__ import annotations

from typing import Iterable

from src.config.runtime_config import RunMode
from src.models.data_models import TradeIntent


class LongHorizonValueRunner:
    def run(self, context):
        """Deterministic watchlist-to-intent adapter for Wave 2 validation."""
        watchlist = self._coerce_watchlist(context)
        mode = self._resolve_mode(context)
        reports = [
            {
                "status": "READY",
                "reason": "LongHorizonValue deterministic fallback pipeline active.",
                "watchlist_k": len(watchlist),
            }
        ]

        intents: list[TradeIntent] = []
        fallback_allowed = mode in {RunMode.SIM, RunMode.PAPER}
        if not fallback_allowed:
            reports.append(
                {
                    "status": "FALLBACK_DISABLED",
                    "reason": "Deterministic fallback is only allowed in SIM/PAPER.",
                    "mode": mode.value,
                }
            )

        for row in watchlist:
            if not fallback_allowed:
                break
            symbol = self._symbol_of(row)
            if not symbol:
                continue
            intent = TradeIntent(
                symbol=symbol,
                direction="LONG",
                strategy_name="LongHorizonValue",
                confidence=0.55,
                rationale="Deterministic long-horizon value fallback: watchlist candidate accepted.",
                trader_type="LONG_HORIZON_VALUE",
                pattern_name="LHV_DETERMINISTIC_FALLBACK",
                data_quality_flags=list(getattr(row, "data_quality_flags", []) or []),
            )
            intents.append(intent)
            # Keep deterministic issuance conservative: single intent per cycle.
            break

        if not intents and watchlist:
            reports.append(
                {
                    "status": "NO_SYMBOLS",
                    "reason": "Watchlist rows missing symbol field.",
                }
            )

        reports.append(
            {
                "status": "SUMMARY",
                "mode": mode.value,
                "trade_intents": len(intents),
            }
        )
        return {"trade_intents": intents, "reports": reports, "metrics": {"watchlist_k": len(watchlist)}}

    @staticmethod
    def _coerce_watchlist(context) -> list[object]:
        if isinstance(context, dict):
            payload = context.get("watchlist")
        else:
            payload = getattr(context, "watchlist", None)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, Iterable):
            return list(payload)
        return []

    @staticmethod
    def _resolve_mode(context) -> RunMode:
        raw = None
        if isinstance(context, dict):
            raw = context.get("mode")
        else:
            raw = getattr(context, "mode", None)
        label = str(raw or RunMode.SIM.value).upper()
        return RunMode.__members__.get(label, RunMode.SIM)

    @staticmethod
    def _symbol_of(row: object) -> str | None:
        if isinstance(row, dict):
            return row.get("symbol")
        return getattr(row, "symbol", None)
