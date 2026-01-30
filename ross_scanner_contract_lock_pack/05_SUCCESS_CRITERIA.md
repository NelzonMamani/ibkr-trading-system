# 05 — Success Criteria (Definition of Done)

A change is DONE only when:

1. Ross Momentum scanner contract is enforced end-to-end:
   - instrument=STK
   - locationCode=STK.US.MAJOR
   - scanCode=TOP_PERC_GAIN
   - abovePrice=1
   - belowPrice=20
   - numberOfRows matches requested TopN (50 live, 150 prep by default)

2. No silent fallbacks:
   - Live modes never produce mock symbols when IBKR is down.
   - Empty watchlist is accepted and still persisted.

3. Single ranking authority:
   - Exactly one layer decides final Ross watchlist ordering.
   - Output is deterministic.

4. Standalone scanner and orchestrator produce consistent symbols/ranking.

5. Tests + verification commands pass without exceptions.

6. Watchlist artifacts exist in `output/watchlists/` for every run and include diagnostics.

Stop after satisfying ALL criteria and producing a PR summary.
