# CONTRACT: Strategy → Execution Intent

## Purpose
Define the canonical intent payload produced by strategies and consumed by execution/risk layers.

## Participants
- **Producer**: Strategy layer (`src/strategies/`, `src/strategy/`)
- **Consumers**: Risk engine (`src/risk/`), execution engine (`src/execution/`)

## Contract Payload (Canonical Fields)
- `intent_id` (string): Unique identifier for the intent.
- `strategy_id` (string): Registered strategy identifier.
- `scan_id` (string): Upstream scan lineage reference (if applicable).
- `symbol` (string): Instrument identifier.
- `side` (enum): buy/sell/short/cover.
- `order_type` (enum): market/limit/stop/other.
- `quantity` (numeric): Target size.
- `price_limit` (numeric or null): Limit price if applicable.
- `time_in_force` (enum): day/gtc/other.
- `timestamp_utc` (ISO-8601 string): Intent creation time.
- `risk_context` (object): Exposure, leverage, stop-loss, take-profit signals.
- `execution_context` (object): Venue preferences, slippage tolerance.
- `mode` (enum): sim/paper/live/read-only.
- `metadata` (object): Namespaced, strategy-specific details.

## Obligations
- Strategy must emit all canonical fields, even if values are null for non-applicable fields.
- Strategy must not emit intents in disallowed modes or when a no-trade context is active.
- Risk engine must validate intent against risk policies before execution.

## Error Handling
- Invalid or missing fields must result in intent rejection and trace emission.
- Conflicting `mode` with runtime must produce a hard stop.

## Versioning
- Contract version tracked in `TRUTH_SOURCE_REGISTRY.md` and M2 Contract Registry.

## Verification Placeholder
- Verification must assert intent schema compliance and risk pre-check acceptance/rejection correctness.
