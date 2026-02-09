# CONTRACT: Scanner → Strategy

## Purpose
Define the canonical data contract between the scanner and strategy layers to prevent silent incompatibilities.

## Participants
- **Producer**: Scanner layer (`src/scanner/`)
- **Consumer**: Strategy layer (`src/strategies/`, `src/strategy/`)

## Contract Payload (Canonical Fields)
- `scan_id` (string): Unique scan session identifier.
- `symbol` (string): Instrument identifier (ticker).
- `timestamp_utc` (ISO-8601 string): Scan event time.
- `market_state` (enum): Normalized market state (open/closed/auction/holiday/etc.).
- `signal_family` (string): High-level signal category.
- `signal_type` (string): Specific signal identifier (maps to M9 registry).
- `confidence` (float 0–1): Confidence score.
- `price_context` (object): Snapshot metrics (bid/ask/last, spread, volume).
- `session_context` (object): Session phase, timezone, venue.
- `risk_flags` (array): No-trade or caution flags derived from E16 taxonomy.
- `metadata` (object): Free-form but namespaced by scanner module.

## Obligations
- Scanner must emit fields above for every scan result that can become a strategy candidate.
- Strategy must reject payloads missing any canonical fields or with non-registered `signal_type`.
- Strategy must record `scan_id` to preserve traceability lineage (E1, M4).

## Error Handling
- If `market_state` is undefined, strategy must route to safe ignore state and log a trace event.
- If `risk_flags` include no-trade contexts, strategy must stop and emit a gated intent artifact.

## Versioning
- Contract version is managed in `TRUTH_SOURCE_REGISTRY.md` and M2 Contract Registry.

## Verification Placeholder
- Verification must assert that every strategy candidate has a valid scanner payload and that all required fields are present.
