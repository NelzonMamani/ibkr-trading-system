# Example Workflow (End-to-End, Conceptual)

This illustrates the intended pipeline without requiring orchestrator code here.

## Example inputs
ScannerFacts (JSON)
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

MarketRegimeFacts (JSON)
```json
{
  "spy_trending_up": false,
  "spy_trending_down": false,
  "qqq_trending_up": false,
  "qqq_trending_down": false,
  "major_macro_event_window": false
}
```

## Example output
```json
{
  "allowed": true,
  "symbol": "XYZ",
  "reason": "APPROVED",
  "setup": "VWAP_EXTENSION_SNAPBACK",
  "diagnostics": {
    "ext_atr": 1.40,
    "exhaustion_score": 2.0,
    "rr": 1.6
  },
  "intent": {
    "symbol": "XYZ",
    "side": "SHORT",
    "entry_type": "LIMIT",
    "entry_price": 10.47,
    "stop_price": 10.78,
    "target_price": 9.85
  }
}
```
