📄 FILE: PHASE_9_STEP_9_1_TRADE_OUTCOME_REALISATION.md
# PHASE 9 — STEP 9.1
# Trade Outcome Realisation (PnL Calculation & Outcome Classification)

## OBJECTIVE
Introduce deterministic trade outcome realisation when trades are CLOSED.
This step must calculate realised PnL, duration, and outcome category
without changing execution, risk, or strategy logic.

This is a READ-ONLY intelligence step.

---

## REQUIRED CHANGES

### 1. Create a new data model: TradeOutcome

Create a new file:

src/domain/trade_outcome.py

Define a dataclass TradeOutcome with the following fields:

- symbol: str
- trader_type: str
- strategy_name: str
- direction: str
- entry_price: float
- exit_price: float
- quantity: int
- realised_pnl: float
- duration_ticks: int
- outcome: str  # WIN | LOSS | FLAT

Outcome rules:
- realised_pnl > 0 → "WIN"
- realised_pnl < 0 → "LOSS"
- realised_pnl == 0 → "FLAT"

PnL calculation rules:
- LONG: (exit_price - entry_price) * quantity
- SHORT: (entry_price - exit_price) * quantity

---

### 2. Extend ExecutionResult to carry exit information

Modify:

src/domain/execution_result.py

Ensure ExecutionResult includes:
- entry_price (already present or inferred)
- exit_price (must be present on CLOSED results)
- entry_tick
- exit_tick

Do NOT change existing constructor usage.
Add defaults if required.

---

### 3. Create TradeOutcomeFactory (pure utility)

Create a new file:

src/core/trade_outcome_factory.py

This factory must:
- Accept a CLOSED ExecutionResult
- Accept strategy_name and trader_type
- Compute:
  - realised_pnl
  - duration_ticks
  - outcome classification
- Return a TradeOutcome instance

This factory must:
- Have no side effects
- Emit no events
- Log nothing

---

### 4. Integrate into TradeExitEngine

Modify:

src/core/trade_exit_engine.py

After trades are CLOSED:
- Generate TradeOutcome objects using TradeOutcomeFactory
- Collect outcomes into a list
- Pass this list forward to storage (next step will persist)

Do NOT:
- Block trades
- Change exit timing
- Affect registry behaviour

---

### 5. Extend TradeRecord to include outcomes

Modify:

src/domain/trade_record.py

Add a new field:
- trade_outcomes: list[TradeOutcome]

Ensure:
- Existing fields remain unchanged
- Construction remains backward-compatible

---

## SAFETY CONSTRAINTS (MANDATORY)

- No behaviour changes to execution or exits
- No PnL aggregation yet
- No persistence changes beyond TradeRecord
- Must work identically in SIM, PAPER, and LIVE
- LIVE mode remains teaching-safe

---

## EXPECTED RESULT

After this step:
- Each closed trade has a deterministic realised outcome
- Outcomes are available for later performance analysis
- No strategy behaviour changes
- No new configuration flags

This step prepares Phase 9.2 (Performance Registry).


When Codex finishes implementing Step 9.1, run the system once and confirm:

Trades still open and close normally

No errors

No behaviour changes

TradeRecord now contains realised outcomes

Then say:

“STEP 9.1 complete — ready for Phase 9 Step 9.2”

And we continue.