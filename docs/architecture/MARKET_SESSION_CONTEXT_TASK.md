# MarketSessionContext — Phase-Aware Trading Control

## PROBLEM
- System uses string-based session logic.
- Phase-sensitive logic (RTH_OPEN, RTH_MID, etc.) is not consistently enforced.
- This can cause incorrect thresholds and missed trades.

## REQUIRED DESIGN
```python
from dataclasses import dataclass

@dataclass
class MarketSessionContext:
    coarse: str   # PRE | RTH | AH | CLOSED
    phase: str    # PRE | RTH_OPEN | RTH_MID | RTH_LATE | AH
    source: str   # TIME | OVERRIDE
```

## REQUIREMENTS
- Replace all string session checks with structured context.
- Apply to:
  - volume gating
  - RVOL normalization
  - pct_change interpretation
  - trigger aggressiveness
  - spread tolerance

## STATUS
DEFERRED — POST TRADE ACTIVATION
