# CONTRACT: Risk Permission Gating

## Purpose
Define canonical gating rules between risk engine, execution engine, and strategy intents.

## Participants
- **Producer**: Risk engine (`src/risk/`)
- **Consumers**: Execution engine (`src/execution/`), strategy orchestration (`src/core/`)

## Contract Payload (Canonical Fields)
- `intent_id` (string): Identifier of the intent under review.
- `decision` (enum): approve/reject/hold.
- `reason_codes` (array): Enumerated reasons mapped to E15 failure taxonomy.
- `timestamp_utc` (ISO-8601 string): Decision time.
- `max_size` (numeric or null): Optional reduced size approval.
- `constraints` (object): Risk constraints applied (max_loss, max_exposure, stop requirements).
- `mode` (enum): sim/paper/live/read-only.
- `risk_flags` (array): Active no-trade or caution flags (E16 taxonomy).

## Obligations
- Execution engine must only execute intents with `decision=approve`.
- Strategy orchestrator must respect `reject` and `hold` decisions without override.
- All decisions must emit trace events (E1) with deterministic reason codes (E15).

## Error Handling
- Missing or malformed decision payloads result in automatic rejection with trace.
- Mode mismatches are treated as hard stops.

## Versioning
- Version managed in `TRUTH_SOURCE_REGISTRY.md` and M2 Contract Registry.

## Verification Placeholder
- Verification must assert deterministic gating behavior and traceability of all decisions.
