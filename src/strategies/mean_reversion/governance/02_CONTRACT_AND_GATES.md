# Mean Reversion — The Immutable Contract (8 Gates)

A mean-reversion trade exists **if and only if** all eight clauses are true:

1) **Abnormal extension**
2) **Continuation failure**
3) **Clear mean**
4) **Confirmed entry**
5) **Hard invalidation**
6) **Defined target**
7) **Regime approval**
8) **Positive asymmetry**

## Non-negotiable rule
If any clause fails → **NO TRADE**.

## Dependency order (mandatory)
The clauses are evaluated in a dependency chain; they are not commutative:

extension → failure → mean → entry → invalidation → target → regime → asymmetry

## Clause definitions (precise)
### 1) Abnormal extension
Price must be materially displaced from the selected mean:
- normalized in ATR multiples (preferred)
- minimum extension threshold enforced
- “too extreme” extension is vetoed as unstable

### 2) Continuation failure
There must be evidence the move is no longer working:
- rejection wick in the direction consistent with reversal
- failed breakout marker aligned with reversal
- optional volume deceleration requirement
The strategy uses a **score** to aggregate evidence; thresholds are explicit.

### 3) Clear mean
A defensible mean reference must exist and be valid:
- VWAP is preferred (default)
- EMA20 or EMA9 may be used as secondary means (if permitted)
If no mean is valid → no trade.

### 4) Confirmed entry
Entries are confirmation-based:
- market entry allowed only for specific “trap unwind” cases (e.g., failed breakout)
- otherwise prefer limit entry to avoid chasing

### 5) Hard invalidation
Stop must be structural:
- HOD/LOD when available, with buffer
- otherwise bounded ATR-buffer fallback
Stops are never widened after entry (governance rule).

### 6) Defined target
Target must be defined before entry:
- mean-touch target with cushion (avoid requiring perfect touch)
May be extended later to multi-target ladders, but must remain predefined.

### 7) Regime approval
Mean reversion is forbidden in hostile regimes:
- strong index trend day
- fresh news / halts
- macro event window
- steep VWAP slope (proxy for trend strength)

### 8) Positive asymmetry
Require minimum R:R given entry, stop, target:
- trade is denied if R:R below threshold
- trade is denied if stop is too wide (ATR-based cap)
