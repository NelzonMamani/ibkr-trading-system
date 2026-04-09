# RUNBOOK UPDATE — PREMARKET LIMIT ORDER REALISM VALIDATION

## 1) Environment prep
- Use IBKR PAPER mode only for validation.
- Ensure market session is premarket (04:00–09:30 America/New_York) if validating premarket behavior.
- Optional tuning knobs (conservative defaults if unset):
  - `PREMARKET_ENTRY_LIMIT_OFFSET_ABS` (default `0.02`)
  - `PREMARKET_EXIT_LIMIT_OFFSET_ABS` (default `0.02`)

## 2) Critical operator warning
- **Close competing TWS/IB Gateway sessions before testing.**
- If you see broker code **10197**, this runbook treats it as a broker environment block (competing session market-data conflict), not strategy failure.

## 3) Required PAPER command
```bash
EXECUTION_MODE=PAPER python -m src.main
```

## 4) Logs you must see
- `[EXECUTION][ORDER_PROFILE]` → session phase + outside-RTH + chosen order type profile.
- `[EXECUTION][PRICE_SOURCE]` and `[EXECUTION][LIMIT_PRICE]` → truthful ask/bid/last source and final limit.
- `[EXECUTION][BROKER_ENV]` → environment blocks (e.g., code 10197).
- `[EXECUTION][BROKER_REJECT_NORMALIZED]` → normalized reject reason.
- `[EXECUTION][NO_FILL_CLASSIFICATION]` → unfilled class (`BROKER_WORKING_UNFILLED`, `PREMARKET_LIMIT_RESTING`, or `BROKER_ENVIRONMENT_BLOCKED`).
- `[EXECUTION][FILL_AUTHORITY]` → confirms `execDetails` remains fill authority.

## 5) Success path (truthful)
1. `SUBMIT` log emitted.
2. ACK callback observed (`openOrder`/`orderStatus`).
3. `execDetails` callback arrives.
4. Fill logs emitted.
5. Position opens from callback-driven fill.

## 6) Failure signatures and meaning
- **10197**: competing live/paper session market-data conflict (`BROKER_ENVIRONMENT_BLOCKED`).
- **Permission/compliance restriction**: normalized broker reject (e.g., `PERMISSION_SMALL_CAP_OPENING_RESTRICTED`).
- **Premarket limit resting with no execDetails**: `PREMARKET_LIMIT_RESTING` (order working, unfilled, no synthetic fill).
