# Data Contract — ScannerFacts (Facts Only)

## Scanner is not allowed to:
- label setups
- decide trades
- compute “should trade” indicators
- override policy thresholds

## ScannerFacts must be strategy-agnostic measurements
Minimum required fields for mean reversion policy:
- symbol
- last
- a valid mean candidate (VWAP preferred; EMA20/EMA9 secondary)
- ATR in dollars

Optional but valuable:
- HOD / LOD
- spread
- failure/exhaustion flags (facts derived from candle/tape measurements)
- minutes_since_open
- vwap_slope

## Example ScannerFacts payload (JSON)
```json
{
  "symbol": "XYZ",
  "last": 10.50,
  "vwap": 9.80,
  "ema9": 10.10,
  "ema20": 9.95,
  "atr": 0.50,
  "hod": 10.70,
  "lod": 9.60,
  "spread": 0.03,
  "volume_deceleration_flag": true,
  "rejection_wick_up_flag": true,
  "failed_breakout_up_flag": false,
  "has_fresh_news": false,
  "halt_flag": false,
  "minutes_since_open": 45,
  "vwap_slope": 0.005
}
```

## Output contract (PolicyDecision)
Policy outputs:
- allowed: bool
- reason: machine-readable reason code
- intent: (if allowed) includes entry_type, entry_price, stop_price, target_price
- diagnostics: numerical fields for audit/debug
