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
        raise NotImplementedError("Mechanics to be implemented by Codex.")
