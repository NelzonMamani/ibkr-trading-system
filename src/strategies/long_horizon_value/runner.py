"""
Strategy Runner Skeleton for Long Horizon Value.
Orchestrator calls this runner; it emits TradeIntents only.
"""

class LongHorizonValueRunner:
    def run(self, context):
        """
        Entry point called by Core Engine.
        This method must:
        - Determine cadence
        - Invoke phases in order
        - Produce TradeIntentBatch (or empty)
        """
        session_phase = None
        if isinstance(context, dict):
            session_phase = context.get("session_phase")
        else:
            session_phase = getattr(context, "session_phase", None)
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

        reports.append(
            {
                "status": "NO_OP",
                "reason": "LongHorizonValue pipeline not yet implemented.",
                "session_phase": session_phase,
            }
        )
        return {"trade_intents": [], "reports": reports, "metrics": {}}
