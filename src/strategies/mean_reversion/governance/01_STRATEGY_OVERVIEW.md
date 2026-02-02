# Mean Reversion Strategy — Overview (Governance)

## Purpose
Mean Reversion is an **intraday counter-momentum strategy** that attempts to capture a controlled snapback
toward a defensible “mean” after **abnormal extension** and **verified continuation failure**.

The strategy is **safe-by-default**:
- If evidence is incomplete or ambiguous → **NO TRADE**
- If a trade is allowed, the policy outputs a structured intent with:
  - side
  - entry style
  - hard stop
  - predefined target

## Architectural rules (immutable)
- **Scanner** provides measurements only (“facts”). It does not label setups and does not decide.
- **Strategy policy** is the only decision brain (trade / no-trade).
- **Risk engine** can veto or constrain, but never creates trades.
- **Execution** places orders and updates state; it is strategy-agnostic.

## What this strategy is NOT
- Not trend-following
- Not averaging down / martingale
- Not prediction-based
- Not discretionary (“it looks stretched” is not a rule)

## Strategy outputs
Per symbol per cycle:
- Allowed = False + explicit reason; OR
- Allowed = True + TradeIntent (entry, stop, target) + diagnostics
