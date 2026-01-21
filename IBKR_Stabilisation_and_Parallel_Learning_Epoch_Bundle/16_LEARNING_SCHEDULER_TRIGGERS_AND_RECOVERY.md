# 16 — LEARNING SCHEDULER, TRIGGERS, AND RECOVERY

## Objective
Make learning run reliably even if the laptop is off at market close.

## Scheduling model
- Learning is “best effort”:
  - it runs when the system is on
  - it can catch up

## Triggers
1. On system startup:
   - if last daily report missing for the last completed NY trading day AND trades exist → generate it.
2. On graceful shutdown:
   - if trades exist today AND daily report missing → generate it.
3. Manual:
   - CLI commands always work.

## “Last completed NY trading day”
Use NY timezone and session calendar.
If market closed today and it’s after close time, that day is eligible.

## Recovery guarantees
- Missing reports are regenerated from DB.
- Learning tables can be recreated from events/TradeRecords (backfill).

## Acceptance criteria
- Turn laptop off; next day startup generates missed report (if there were trades).
- No repeated duplication (idempotent report IDs / hash-based).

END
