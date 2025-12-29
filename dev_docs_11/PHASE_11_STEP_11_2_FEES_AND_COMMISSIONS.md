# PHASE_11_STEP_11_2_FEES_AND_COMMISSIONS.md

## PHASE 11 — MARKET REALISM LAYER
### STEP 11.2 — Deterministic Fees & Commissions Model

## OBJECTIVE
Introduce a deterministic, replay-safe fees and commissions system that:

- Applies broker-style costs to every completed trade
- Reduces realised PnL accordingly
- Preserves determinism and replay correctness
- Does NOT alter strategy, risk, or execution timing
- Builds cleanly on Phase 11.1 slippage

Fees must be:
- Deterministic
- Transparent
- Event-driven
- Fully reconstructible from replay

---

## DESIGN RULES (MANDATORY)

1. NO randomness
2. NO time-based values
3. NO external broker calls
4. NO strategy changes
5. NO risk engine changes
6. NO orchestrator flow changes
7. Replay must reconstruct identical net PnL
8. Fees applied ONLY on trade close

---

## COMMISSION MODEL (DETERMINISTIC)

Use a fixed per-share commission model:

| Trader Type | Commission per Share |
|------------|----------------------|
| SCALPER    | 0.005                |
| MOMENTUM  | 0.007                |

Rules:
- Commission applies on BOTH entry and exit
- Total commission = quantity × commission_per_share × 2
- Commission always reduces realised PnL
- Commission is always positive (cost)

---

## IMPLEMENTATION TASKS

### 1. CREATE NEW MODULE

Create file:

src/execution/commission_model.py

Contents:
- CommissionModel class
- Static method:

  calculate_commission(
      trader_type: str,
      quantity: int
  ) -> float

This returns TOTAL commission for the round-trip trade.

---

### 2. UPDATE TRADE EXIT LOGIC

File:
src/execution/trade_exit_engine.py (or equivalent close logic)

Steps:
1. After computing gross realised_pnl
2. Call CommissionModel.calculate_commission(...)
3. Compute:
   net_realised_pnl = gross_realised_pnl - commission
4. Store BOTH values:
   - gross_realised_pnl
   - commission
   - net_realised_pnl

---

### 3. UPDATE TRADE OUTCOME MODEL

File:
src/execution/trade_outcome.py (or equivalent)

Add fields:
- gross_realised_pnl: float
- commission: float
- net_realised_pnl: float

Maintain backward compatibility:
- If commission missing, assume 0.0

Outcome classification (WIN / LOSS / FLAT) must be based on:
- net_realised_pnl

---

### 4. UPDATE EVENTS

Ensure TRADE_CLOSED event payload includes:
- gross_realised_pnl
- commission
- net_realised_pnl

Replay must use net_realised_pnl for performance reconstruction.

---

### 5. UPDATE PERFORMANCE REGISTRY

File:
src/performance/performance_registry.py (or equivalent)

Changes:
- Aggregate net_realised_pnl (not gross)
- Track:
  - total_commissions
  - gross_pnl
  - net_pnl

Expose in PERF_SNAPSHOT:
- gross_pnl
- total_commissions
- net_pnl
- avg_net_pnl_per_trade

---

### 6. UPDATE REPLAY LOGIC (IF REQUIRED)

If replay reconstructs PnL:
- Use net_realised_pnl from events
- DO NOT recompute commissions during replay

Replay must be event-driven only.

---

## VALIDATION REQUIREMENTS

After implementation:

1. Phase 10 trade lifecycle unchanged
2. Phase 11.1 slippage unchanged
3. Gross PnL visible
4. Commission visible
5. Net PnL reduced correctly
6. WIN/LOSS classification reflects net PnL
7. Replay reproduces identical net results
8. Invariants pass
9. No schema warnings
10. No randomness introduced

---

## FORBIDDEN ACTIONS

- Do NOT modify orchestrator
- Do NOT modify strategy logic
- Do NOT modify risk limits
- Do NOT modify slippage rules
- Do NOT introduce broker APIs
- Do NOT break replay determinism

---

## COMPLETION CRITERIA

Phase 11 · Step 11.2 is COMPLETE when:
- Every closed trade includes commission
- Net PnL is correctly reduced
- Performance reports show gross vs net
- Replay reconstructs identical results

END OF INSTRUCTIONS