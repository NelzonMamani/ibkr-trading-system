# Mode Requirements (Critical)

## SIM
- Full lifecycle simulated
- No broker calls

## PAPER
- Uses paper execution provider
- Trades recorded

## LIVE_READ_ONLY
- Strategy runs
- Decisions logged
- No orders sent

## LIVE_MICRO
- Orders capped to 1 share
- Safety-first

## LIVE
- Full execution
- All risk constraints enforced

Mode switching must NOT alter strategy logic.
