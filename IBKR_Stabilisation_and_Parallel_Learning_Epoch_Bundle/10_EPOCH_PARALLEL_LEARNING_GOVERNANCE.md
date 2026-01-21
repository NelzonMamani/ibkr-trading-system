# 10 — EPOCH: PARALLEL LEARNING (GOVERNANCE)

## Purpose
Add a **Parallel Learning Epoch** that:
- learns from **stored events/trade records** and external reference data when appropriate
- produces **reports** and **policy proposals**
- never mutates live trading logic automatically

This epoch is designed to run while the system trades live.

## Non-negotiable governance rules
1. **No automatic mutation**
   - Learning outputs are proposals only.
   - Activation requires manual approval (human) and a controlled config change.

2. **No structural divergence**
   - Strategy policy schemas are stable contracts.
   - Learning proposals may only change **numeric threshold values** and boolean toggles explicitly marked “tunable”.
   - Any new field requires a separate governance phase and explicit approval.

3. **Ross baseline is immutable**
   - `ROSS_MOMENTUM` baseline policy file/spec is the reference.
   - Learned variants must be stored as:
     - `ROSS_MOMENTUM__PROPOSED__<timestamp>.json`
     - or a versioned dataclass serialisation
   - Never overwrite `ROSS_MOMENTUM` baseline.

4. **Determinism**
   - Given the same event history, learning output must be reproducible (seeded randomness if needed).

5. **Separation of concerns**
   - Live trading pipeline remains in `src/strategy`, `src/core`, `src/execution`.
   - Learning pipeline lives under `src/learning/` (or equivalent).

## Outputs (minimum)
- Daily/weekly/monthly/yearly reports (summaries + diagnostics)
- Pattern and rule adherence analysis
- Policy proposal candidates after sufficient sample size
- “Why did we not trade?” explanations where possible, grounded in logged gates

## Entry points
Provide:
- CLI: `python -m src.learning.cli --help`
- Subcommands:
  - `report --date YYYY-MM-DD --strategy ROSS_MOMENTUM`
  - `propose-policy --strategy ROSS_MOMENTUM --min-trades 30`
  - `summarise --last N`
  - `backfill --from YYYY-MM-DD --to YYYY-MM-DD` (optional)

## Data sources (preferred)
- Primary: existing **events** + **TradeRecord** + **Performance snapshots**
- Secondary (optional): market reference data (index regime, vol)
- External news/fundamentals is allowed only for **explanations**, not for rewriting history.

## Definition of Done for the Learning Epoch
- Learning module can run with **zero trades** and produce a “no data yet” report.
- After trades exist, it produces:
  - daily report with lessons and rule adherence
  - policy proposal artifacts after threshold count (e.g., 30/100 trades)

END
