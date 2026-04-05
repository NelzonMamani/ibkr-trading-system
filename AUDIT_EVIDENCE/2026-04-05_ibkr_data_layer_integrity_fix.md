# IBKR Data Layer Integrity Audit Evidence (2026-04-05)

## Root Cause
IBKR snapshot payloads with invalid quote values (`last=None/-1`, `bid=-1`, `ask=-1`) were allowed into scanner context as if they were canonical market quotes. This enabled downstream percent-change and spread derivation from invalid fields.

## Corrupt Values Previously Observed
- `last=None` or `last<=0` propagated as effective current price candidate.
- `bid/ask<=0` were not hard-blocked before spread derivation.
- Percent-change could be derived using non-canonical fallback behavior.

## Invariants Added
1. Canonical last price requires `last>0`; no bid/ask midpoint fallback for canonical current price.
2. Spread derivation requires `bid>0` and `ask>0`; otherwise spread is unavailable.
3. Previous close remains reference only (`reference_prev_close`), never substituted as current last.
4. Snapshot output now carries explicit integrity contract including:
   - requested/effective market data type,
   - validity booleans,
   - `quote_integrity_state`,
   - integrity flags.
5. Scanner watchlist gates now explicitly drop invalid quote contexts with integrity reasons.

## Verification Commands Run
- `pytest -q tests/test_market_data_client_snapshot.py tests/test_ibkr_data_integrity_layer.py`
- `pytest -q tests/test_scanner_pct_change_fallback.py`

## Residual Limitations
- Behavior in true live permission-limited IBKR environments still depends on account entitlements; local tests use deterministic stubs.
- Real-world callback timing for IBKR market-data-type transitions can vary; this change records effective ticker market-data type when available.

## Outcome
System now fails truthfully (explicit integrity/unavailable states and drop reasons) instead of failing corruptly via fabricated momentum inputs.
