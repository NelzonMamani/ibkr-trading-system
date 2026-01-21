# 11 — LEARNING DATA MODEL, STORAGE, AND BACKFILL

## Objective
Use existing persisted artifacts (events / trade records) as the canonical learning source. Avoid a second DB unless strictly necessary.

## Decision: separate learning DB?
Default: **NO**.
- Use the existing SQLite DB and add learning tables if needed.
- Rationale: events already exist; learning is derived.

Allow separate DB only if:
- performance becomes an issue, or
- you want to keep learning artifacts portable.

If a separate DB is introduced, it must be:
- read-only with respect to live trading
- rebuildable from the primary DB

## Required learning tables (minimal additions)
1. `learning_runs`
   - run_id (uuid), started_at_utc, completed_at_utc, ok, error
   - strategy_name, window_start_utc, window_end_utc
   - inputs_hash, outputs_hash

2. `learning_reports`
   - report_id, run_id, report_type (DAILY/WEEKLY/MONTHLY/YEARLY)
   - asof_date_ny, strategy_name
   - payload_json (full report)
   - summary_text (short)

3. `policy_proposals`
   - proposal_id, created_at_utc
   - strategy_name, baseline_policy_version
   - min_trades_required, trades_used
   - proposal_json (same schema as baseline policy)
   - diff_json (field→old/new)
   - rationale_json (field→reason)
   - status (DRAFT/REVIEWED/APPROVED/REJECTED)
   - approved_by, approved_at_utc

## Normalised learning view (in code)
Create a stable in-memory representation:
### LearningTrade (derived from TradeRecord + events)
- strategy_name
- symbol
- entry_time, exit_time
- entry_price, exit_price
- pnl, pnl_pct
- tags: patterns, session_phase, setup_type
- gate_context:
  - scanner metrics at decision time (price/gap/rvol/float/volume/spread/catalyst)
  - risk decisions
  - reasons for reject (if no trade)

### LearningDataset
- list[LearningTrade]
- aggregates (computed lazily)

## Backfill logic
When no learning tables exist:
- backfill derived LearningTrade objects from historical TradeRecords
- store summaries and proposal eligibility counters

Backfill must be:
- idempotent
- safe if DB is empty
- fast enough to run daily

## “Why did we not trade?” support
This requires the live pipeline to log gate failures deterministically.
Learning module should read:
- scanner drop_reasons
- pattern engine “no pattern” notes
- signal engine “no signals” notes
- strategy “returned empty” reasons (if present)
If these are missing, create minimal event payloads to capture:
- reason codes (not free text only)

## Tests
- test that learning module can run with:
  - empty DB
  - DB with events only
  - DB with 1–2 TradeRecords
- test idempotent backfill

END
