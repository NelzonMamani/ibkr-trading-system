# Scanner Event Model

The scanner is a *fact producer*.

## Mandatory Events

### SCANNER_UNIVERSE_SNAPSHOT
Emitted every scan cycle.
Includes:
- symbols
- requested_rows
- returned_rows
- session
- timestamp

### SCANNER_SYMBOL_DROPPED
Emitted per symbol.
Includes:
- symbol
- drop_reason
- metric_value
- threshold

### SCANNER_WATCHLIST_K_READY
Emitted after gates and ranking.
Includes:
- watchlist_k
- K
- policy_name

### SCANNER_MOMENTUM_SPIKE (optional)
Emitted when momentum accelerates intraday.

The scanner never decides trades.