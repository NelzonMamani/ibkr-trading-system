# 99 — CODEX MASTER INSTRUCTION BLOCK (COPY/PASTE AS ONE BLOCK)

You are Codex working in the repository `ibkr-trading-system`.

GOAL:
Lock the scanner contract for Ross Momentum so the system produces a correct Ross watchlist (small caps, $1–$20) using IBKR `TOP_PERC_GAIN` on `STK.US.MAJOR`, with no universe drift and no silent MOCK fallback in live modes. Ensure prep-mode behavior when market is closed still produces a prep report and persisted watchlist artifact (even if empty).

RULES:
- Single PR. No parallel work. No refactors unless required.
- Do not change Ross strategy logic/patterns unless necessary for contract locking.
- Do not weaken tests. Add tests if needed.
- You MUST run the Mandatory Verification Commands and make them pass before stopping.

IMPLEMENTATION PLAN (DO IN ORDER):

1) TRACE THE CURRENT CALL PATH
- Identify where Ross stock selection policy is converted into scanner inputs.
- Identify where scanCode/locationCode/abovePrice/belowPrice/rows are currently set.
- Confirm current behavior that allowed large-cap symbols into Ross watchlist (AAPL/TSLA/PLTR).

2) INTRODUCE/CONFIRM A STRATEGY SCANNER REQUEST OBJECT
- Implement a request structure (dataclass or dict) that carries:
  instrument, locationCode, scanCode, abovePrice, belowPrice, numberOfRows, strategy_name, policy_name, ranking_intent, session_phase.
- Ensure orchestrator constructs this request from `strategies/ross_momentum/strategy_policy.py` `StockSelectionSpec`.
- Default for Ross:
  - abovePrice=1
  - belowPrice=20
  - scanCode=TOP_PERC_GAIN
  - locationCode=STK.US.MAJOR
  - instrument=STK
  - numberOfRows:
    - 150 when session_phase=CLOSED or explicit prep run
    - 50 otherwise
- Log the resolved request in orchestrator.

3) MAKE IBKR PROVIDER CONSUME THE REQUEST (NO HARDCODE CONFLICT)
- Update `IbkrScannerProvider.get_top_gainers(...)` (or add a new method) so it uses the request parameters.
- Maintain existing API compatibility if other callers depend on `limit` only.
- Print `[SCANNER][IBKR][SUBSCRIPTION] ...` with the resolved parameters every time.

4) REMOVE SILENT MOCK FALLBACK IN LIVE MODES
- In LIVE/LIVE_READ_ONLY/LIVE_MICRO:
  - If provider connection fails, return `[]` universe symbols.
  - Continue pipeline to produce diagnostics + watchlist artifact (empty is OK).
  - Do NOT inject mock symbols.
- In SIM/PAPER:
  - MOCK allowed only if explicitly selected; must be clearly printed as `provider=MOCK`.
- Make fallback behavior explicit and test-covered.

5) ENFORCE SINGLE RANKING AUTHORITY FOR ROSS
- Choose strategy-owned ranking:
  - `strategies/ross_momentum/strategy_policy.select_watchlist` is the final ranking authority (reverse=True).
  - Remove/disable orchestrator re-ranking for Ross watchlist selection OR ensure orchestrator does not re-sort when strategy already returns watchlist.
  - scanner_runner should not decide Ross watchlist ordering beyond stable printing.
- Add a comment in code marking the authority for Ross.

6) ALIGN STANDALONE SCANNER WITH STRATEGY SELECTION
- Ensure `python -m src.scanner.scanner_main --strategy ross_momentum` uses the same request construction as orchestrator and the same provider behavior.
- Add CLI flags if needed: `--strategy`, `--session`, `--topn`.
- Ensure output includes WATCHLIST_K, FOCUS_M, NEW/CONTINUING/DROPPED and writes artifact.

7) PREP MODE WHEN MARKET IS CLOSED
- In CLOSED session phase:
  - Request TopN=150 for Ross by default.
  - Run cheap gates and persist watchlist artifact.
  - If IBKR unavailable, persist empty artifact with reasons.

8) TESTS
- Add/update tests to verify:
  - Ross request produces correct subscription params (instrument/locationCode/scanCode/above/below/rows).
  - Live modes do not inject mock symbols on IBKR failure.
  - Watchlist artifact is created even when universe empty.
  - Ranking is deterministic and single-authority.

9) RUN MANDATORY VERIFICATION COMMANDS
- Execute commands in `04_MANDATORY_VERIFICATION_COMMANDS.md`.
- If anything fails, fix and rerun until all pass.

DELIVERABLES:
- Code changes + tests + updated docs if needed.
- A short PR summary describing:
  - where the contract is enforced,
  - how fallback behaves per mode,
  - where ranking authority lives,
  - evidence from verification logs.

STOP ONLY WHEN ALL VERIFICATION COMMANDS PASS.
