# 38_PHASE_7_STEP_7_2_CODEX_INSTRUCTIONS_TRADE_CLOSE_PRICE_AND_REALIZED_PNL.md

# PHASE 7 — TIME & PNL FOUNDATIONS
## STEP 7.2 — CLOSE PRICE + REALISED PNL (SIM-ONLY) + TRADE_CLOSED PAYLOAD

You are Codex operating on the IBKR Trading System repository.

You will implement SIM-only realised PnL at close time using the deterministic price feed.
This MUST remain teaching-first and deterministic.

---

## OBJECTIVE

You will:

- Capture a deterministic CLOSE tick and CLOSE price when SIM trades are closed
- Compute realised PnL for LONG trades (teaching-only)
- Store close metadata in the trade lifecycle
- Emit TRADE_CLOSED events with: close_tick, close_price, realised_pnl
- Keep RUN_MODE safe: only compute PnL in SIM

---

## FILES TO MODIFY (ONLY THESE)

- src/core/active_trade_registry.py
- src/execution/execution_engine.py
- src/events/system_events.py (if TRADE_CLOSED payload exists)
- src/storage/storage_engine.py (optional: log-only, still no persistence)

Do not modify any other files.

---

## STEP 1 — EXTEND ActiveTrade TO INCLUDE CLOSE FIELDS

Modify:

src/core/active_trade_registry.py

Extend the ActiveTrade dataclass to include optional close metadata:

- close_tick: int | None
- close_price: float | None
- realised_pnl: float | None

Rules:
- Entry fields remain required
- Close fields default to None
- realised_pnl is computed at close in SIM mode only

Example (adapt as needed):

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ActiveTrade:
    symbol: str
    trader_type: str
    entry_tick: int
    entry_price: float
    close_tick: Optional[int] = None
    close_price: Optional[float] = None
    realised_pnl: Optional[float] = None
```

---

## STEP 2 — ADD REGISTRY SUPPORT TO FETCH ACTIVE TRADE OBJECT

Modify:

src/core/active_trade_registry.py

Add a method:

- get_trade(symbol: str, trader_type: str) -> ActiveTrade | None

This must return the stored ActiveTrade instance.

Also add a method:

- mark_closed(symbol, trader_type, close_tick, close_price, realised_pnl)

This updates the existing stored trade before it is unregistered
(so teaching logs can show it clearly).

Add logs:

```text
[REGISTRY] MARK_CLOSED symbol=ABC trader_type=SCALPER close_tick=1 close_price=12.37 realised_pnl=0.00
```

---

## STEP 3 — COMPUTE REALISED PNL ON SIM CLOSE

Modify:

src/execution/execution_engine.py

Where you currently simulate close:

```text
[EXECUTION] Simulating trade CLOSE for ABC (SCALPER)
```

Replace/augment logic:

1. Determine close_tick = current cycle tick (same tick used in cycle)
2. Determine close_price via DeterministicPriceFeed.price_for(symbol, close_tick)
3. realised_pnl calculation rule (teaching-only):
   - LONG only
   - position_size is always 1 share in current teaching rules
   - pnl = round(close_price - entry_price, 2)

4. Update registry via mark_closed(...)
5. Emit TRADE_CLOSED event including payload:
   - symbol, trader_type
   - entry_tick, entry_price
   - close_tick, close_price
   - realised_pnl

6. Then unregister trade (keep current unregister behaviour)

Required logs:

```text
[PRICE_FEED] symbol=ABC tick=1 price=12.37
[EXECUTION] CLOSE symbol=ABC tick=1 close_price=12.37 realised_pnl=0.00 (SIM)
[EVENT] TRADE_CLOSED emitted for ABC (SCALPER) tick=1 price=12.37 pnl=0.00
```

IMPORTANT:
- This must only occur when run_mode == SIM
- In LIVE mode, do not compute pnl and do not create fake close prices

---

## STEP 4 — ENSURE EVENT PAYLOADS ARE UPDATED

Modify:

src/events/system_events.py (only if needed)

Ensure TRADE_CLOSED payload contains all close fields.

---

## VALIDATION REQUIREMENTS

After implementation, running in SIM should show:

- Entry price logged
- Close price logged
- realised_pnl logged deterministically
- Replay remains deterministic
- No randomness
- No broker calls

---

## COMPLETION MESSAGE

When done, respond with:

“PHASE 7 STEP 7.2 complete — ready for Step 7.3”
