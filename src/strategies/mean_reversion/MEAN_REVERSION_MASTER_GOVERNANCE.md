# MEAN REVERSION STRATEGY — MASTER GOVERNANCE DOCUMENT
Generated: 2026-02-02 07:25:48Z

---

## 1. Strategy Overview

Mean Reversion is an **intraday counter‑momentum strategy** designed to capture snapbacks toward a
defensible mean after **abnormal extension** and **verified continuation failure**.

Safe‑by‑default rule:
If evidence is incomplete or ambiguous → **NO TRADE**.

Architectural constraints:
- Scanner provides facts only
- Strategy policy decides
- Risk engine may veto
- Execution is downstream and logic‑free

---

## 2. Immutable Strategy Contract (8 Clauses)

A trade exists **if and only if** ALL clauses are satisfied:

1. Abnormal extension  
2. Continuation failure  
3. Clear mean  
4. Confirmed entry  
5. Hard invalidation  
6. Defined target  
7. Regime approval  
8. Positive asymmetry  

Failure of any clause → **NO TRADE**.

---

## 3. Clause Definitions

### Clause 1 — Abnormal Extension
Price must be displaced from the mean by a minimum ATR‑normalized threshold.
Extensions beyond a maximum ATR are rejected as unstable.

### Clause 2 — Continuation Failure
Evidence the move has stalled or failed:
- rejection wicks
- failed breakouts
- volume deceleration  
Evidence is scored; thresholds are explicit.

### Clause 3 — Clear Mean
A valid, defensible mean must exist:
- VWAP (primary)
- EMA20 / EMA9 (secondary, optional)

### Clause 4 — Confirmed Entry
Entries are confirmation‑based:
- Market entries allowed only for trap unwinds
- Limit entries preferred otherwise

### Clause 5 — Hard Invalidation
Stops are structural:
- HOD / LOD when available
- ATR‑buffer fallback otherwise  
Stops are never widened.

### Clause 6 — Defined Target
Target must be predefined before entry:
- Mean‑touch with cushion

### Clause 7 — Regime Approval
Trades are forbidden during:
- index trend days
- fresh news or halts
- macro event windows
- steep VWAP slope

### Clause 8 — Positive Asymmetry
Minimum R:R required.
Maximum stop width enforced.

---

## 4. Data Contract — ScannerFacts

Scanner emits measurements only.
No setup labels. No decisions.

Minimum required:
- symbol
- last
- ATR
- valid mean candidate

Optional but valuable:
- HOD / LOD
- spread
- exhaustion flags
- minutes since open
- VWAP slope

---

## 5. Decision Workflow Algorithm

High‑level loop:
1. Receive ScannerFacts per symbol
2. Receive MarketRegimeFacts
3. Apply clauses in order
4. Emit PolicyDecision

Pseudo‑code (authoritative):

```
for symbol:
  if invalid price → deny
  if regime veto → deny
  if no ATR → deny
  mean = select_mean()
  if no mean → deny
  ext = extension_in_ATR()
  if ext < min or ext > max → deny
  side = above_mean ? SHORT : LONG
  if no exhaustion → deny
  entry = structural_entry()
  if none → deny
  stop = compute_stop()
  if too wide → deny
  target = compute_target()
  if RR < min → deny
  approve TradeIntent
```

---

## 6. Setup Library

- VWAP_EXTENSION_SNAPBACK
- EMA_STRETCH_REVERSION
- FAILED_BREAKOUT_REVERSION
- EXHAUSTION_SPIKE_TIME_REVERSION

Setups are labels only.
They do not bypass the contract.

---

## 7. Risk & Position Governance

- Hard stop + target mandatory
- No averaging down
- Risk engine may veto or size
- Strategy never removes constraints

---

## 8. Failure Modes & Safeties

Failure modes:
- fading trends
- chasing entries
- loose stops
- illiquidity

Safeties:
- safe‑by‑default
- regime veto
- stop width cap
- RR gate

---

## 9. Testing & Verification Expectations

Invariants:
- any clause fail → allowed = False
- allowed = True → stop + target exist
- deterministic outputs

---

## 10. Phased Implementation Roadmap (Informational)

1. Governance ingestion
2. Type alignment
3. Orchestrator wiring
4. Data provisioning
5. Risk integration
6. Paper simulation
7. Live micro
8. Enhancements

---

## 11. Example Workflow

Input (ScannerFacts):
```
symbol=XYZ
last=10.50
vwap=9.80
atr=0.50
rejection_wick_up=True
volume_deceleration=True
```
Output:
```
SHORT @ 10.47
STOP 10.78
TARGET 9.85
RR 1.6
```
