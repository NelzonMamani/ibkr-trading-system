# PR #792 Follow-up Audit Evidence — Quote Validity Contract Split

## Why the first implementation broke tests

The first hardening pass treated scanner continuity, momentum truth, and execution truth as one validity contract. That collapsed non-execution paths (PRE/AH/reference-only and handcrafted runtime tests) by failing symbols before the intended domain gate (float/volume/focus/routing) could evaluate.

## Contract introduced in this repair

This patch introduces three explicit quote usability contracts in scanner context and gate handling:

- `quote_valid_for_scanner`: permissive, session-aware continuity contract.
- `quote_valid_for_momentum`: strict momentum truth contract (`valid last` + `valid reference`).
- `quote_valid_for_execution`: strict execution contract (`valid last` + `valid bid` + `valid ask`).

Additional explicit state:

- `current_quote_available`
- `pct_change_available`
- `spread_available`
- `quote_integrity_state`
- `scanner_quote_policy`
- `quote_degraded_reason_codes`

## Why strict IBKR truth is preserved

- Canonical `last_price` is now derived from IBKR `last` only when strictly valid (>0).
- No midpoint, bid, or ask fallback is used as canonical current price.
- Momentum validity requires both valid current last and valid reference.
- Execution validity remains strict top-of-book + last.
- Degraded scanner continuity is explicit via policy and reason codes, never silently treated as momentum/execution truth.

## Restored test and runtime behavior

The watchlist gate now performs scanner-validity inference for handcrafted contexts when explicit validity fields are missing, preserving backward compatibility for direct test contexts and runtime routing tests.

Restored behavior includes:

- Non-empty scanner/watchlist/focus routing continuity in SIM/runtime tests.
- PRE/AH degraded continuity allowed without fabricating momentum.
- Float/volume/focus gates can fail first when appropriate, instead of premature quote invalid drops.

## Residual limitations

- Degraded PRE/AH continuity still depends on explicit session normalization; malformed session labels may degrade to strict handling.
- This patch intentionally does not relax execution or momentum requirements in any mode.
