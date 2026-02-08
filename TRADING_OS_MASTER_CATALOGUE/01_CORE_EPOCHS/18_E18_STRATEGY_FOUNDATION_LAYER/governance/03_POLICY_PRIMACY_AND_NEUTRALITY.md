# E18 — POLICY PRIMACY & FOUNDATION NEUTRALITY (SYSTEM LAW)

PRINCIPLE: STRATEGY POLICY IS SOVEREIGN
- The OS must never impose a trading style.
- The OS may provide defaults, but defaults must be optional and overrideable.
- A “simple/dumb” strategy must remain viable and protected (risk, safety, gating).
- A specialized strategy must have its unique rules respected (not diluted by defaults).

FOUNDATION NEUTRALITY RULES:
- Foundation primitives are context-agnostic and composable.
- No primitive may embed “Ross-only” assumptions or enforce Ross gates globally.
- No primitive may force indicator usage (MACD/EMA/VWAP). Indicators are optional inputs.
- Strategies choose which primitives to use and how to combine them.

FORBIDDEN:
- Strategy-local re-implementation of foundation primitives without explicit declaration.
- Silent policy overrides via foundation defaults.
- Implicit coupling between strategy policy and foundation internals.

REQUIRED:
- Strategy ↔ Foundation mapping must be explicit, auditable, and drift-detectable.

END
