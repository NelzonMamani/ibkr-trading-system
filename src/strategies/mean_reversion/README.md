# Mean Reversion Strategy — Governance Bundle

This folder is designed to be **Codex-readable** and **phase-implementable**.
It contains:
- The **authoritative policy brain** (`mean_reversion_strategy_policy.py`)
- Governance and contracts that prevent drift
- Placeholders for clause-specific models Codex can expand later

## Non-Negotiable Contract
A mean-reversion trade exists only if all eight are true:
1. Abnormal extension
2. Continuation failure
3. Clear mean
4. Confirmed entry
5. Hard invalidation
6. Defined target
7. Regime approval
8. Positive asymmetry

If any clause fails → **NO TRADE**.

## Architecture
- Scanner provides facts only.
- Policy is the only decision maker.
- Risk engine can veto.
- Execution is downstream and unaware of strategy logic.
