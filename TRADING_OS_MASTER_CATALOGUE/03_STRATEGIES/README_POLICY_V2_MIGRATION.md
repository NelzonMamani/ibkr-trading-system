# StrategyPolicyV2 migration note

This change introduces `StrategyPolicyV2` as a **spec-only** contract and adds per-strategy `POLICY_V2` modules for P01-P20.

No runtime wiring is changed in this PR. Orchestrator/scanner/execution integration for V2 is intentionally deferred to a follow-up PR after review.
