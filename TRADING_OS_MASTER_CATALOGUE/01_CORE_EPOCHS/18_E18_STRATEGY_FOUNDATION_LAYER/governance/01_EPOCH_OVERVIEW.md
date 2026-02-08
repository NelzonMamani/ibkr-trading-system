# E18_STRATEGY_FOUNDATION_LAYER — OVERVIEW

E18 establishes the shared, reusable Strategy Foundation Layer used by ALL strategies.

E18 exists to:
- Provide canonical primitives (setups, triggers, conditions, confirmations, candlesticks)
- Provide neutral context primitives (levels, zones, structure states)
- Provide fast symbol context hydration upon commitment
- Provide resettable, regenerable derived state
- Provide policy translation + drift detection so strategies remain aligned over time

After E18:
- Strategies compose foundation primitives; they do not re-implement them.
- The Trading OS can scale to many strategies without fragmentation.
- The system can evolve foundations safely with versioning and compatibility proofs.

END
