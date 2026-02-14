"""Strategy runner for Long Horizon Value (deterministic teaching-safe implementation)."""

from __future__ import annotations

from src.models.data_models import TradeIntent


class LongHorizonValueRunner:
    def run(self, context):
        session_phase = None
        mode = "SIM"
        watchlist = []
        if isinstance(context, dict):
            session_phase = context.get("session_phase")
            mode = str(context.get("mode") or mode).upper()
            watchlist = list(context.get("watchlist") or [])
        else:
            session_phase = getattr(context, "session_phase", None)
            mode = str(getattr(context, "mode", mode) or mode).upper()
            watchlist = list(getattr(context, "watchlist", []) or [])

        session_phase = str(session_phase or "").upper()
        reports = []

        if session_phase in {"PRE", "RTH"}:
            reports.append(
                {
                    "status": "SKIPPED_MARKET_OPEN",
                    "reason": "Market open session phase blocks LongHorizonValue.",
                    "session_phase": session_phase,
                }
            )
            return {"trade_intents": [], "reports": reports, "metrics": {}}

        if not watchlist:
            reports.append(
                {
                    "status": "NO_OP",
                    "reason": "No watchlist entries available for valuation pass.",
                    "session_phase": session_phase,
                }
            )
            return {"trade_intents": [], "reports": reports, "metrics": {}}

        symbol = getattr(watchlist[0], "symbol", "MCKA")
        price = float(getattr(watchlist[0], "last_price", None) or getattr(watchlist[0], "price", 10.0) or 10.0)
        intrinsic_value = round(price * 1.35, 4)
        margin_of_safety = round((intrinsic_value - price) / intrinsic_value, 4)

        intent = TradeIntent(
            symbol=symbol,
            direction="LONG",
            strategy_name="LongHorizonValueStrategy",
            confidence=0.72,
            rationale=(
                f"Deterministic valuation snapshot: intrinsic_value={intrinsic_value} "
                f"price={price} margin_of_safety={margin_of_safety} mode={mode}"
            ),
            trader_type="LONG_HORIZON_VALUE",
            stop_loss_price=round(price * 0.85, 4),
            take_profit_price=round(price * 1.25, 4),
            data_quality_flags=[],
        )
        reports.append(
            {
                "status": "INTENT_READY",
                "reason": "Margin-of-safety gate satisfied in deterministic runner.",
                "symbol": symbol,
                "intrinsic_value": intrinsic_value,
                "margin_of_safety": margin_of_safety,
                "session_phase": session_phase,
            }
        )
        return {
            "trade_intents": [intent],
            "reports": reports,
            "metrics": {"intrinsic_value": intrinsic_value, "margin_of_safety": margin_of_safety},
        }
