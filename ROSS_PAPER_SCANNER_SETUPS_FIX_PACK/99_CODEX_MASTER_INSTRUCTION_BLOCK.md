# 99_CODEX_MASTER_INSTRUCTION_BLOCK.md
TITLE: CODEX MASTER INSTRUCTION BLOCK — Scanner → PAPER → Ross Setups (Ordered)
DATE: 2026-01-31

INSTRUCTIONS FOR CODEX (COPY/PASTE AS ONE BLOCK)

FILE: 99_CODEX_MASTER_INSTRUCTION_BLOCK.md
TITLE: CODEX MASTER INSTRUCTION BLOCK — Scanner → PAPER → Ross Setups (Ordered)

You are working in the repository: `ibkr-trading-system`.

Mission: Make the system tradable by automating Ross’s workflow end-to-end. Execute the steps below IN ORDER with mandatory verification. Do not stop early. Do not implement partial steps and move on.

GLOBAL RULES:
1) No parallel PRs. One linear sequence of changes.
2) Scanner emits facts only; strategy decides.
3) Execution modes are only: PAPER, LIVE_READ_ONLY, LIVE. Remove/deprecate SIM and remove LIVE_MICRO modes (replace with risk profiles).
4) Risk profiles are orthogonal and config-only. Use `src/config/risk_profiles.py` already pushed by the user. Implement `RISK_PROFILE=MICRO` (1 share clamp) and allow intermediate profiles (e.g., SMALL).
5) All changes must work across sessions: CLOSED/PRE/RTH/AH.

================================================================================
STEP 1 — SCANNER CORRECTION (SESSION CONTRACT)
================================================================================
1.a Implement a single authoritative session detector used across the system that yields:
- session_label (CLOSED/PRE/RTH/AH)
- next_session_label
- session start/end timestamps
- last_rth_close timestamp
- weekend/holiday flags

1.b Enforce a “reference price contract” in scanner output:
- reference_price_type in {RTH_CLOSE, PRIOR_RTH_CLOSE, PRE_MARKET_OPEN, LAST_TRADE, LAST_AVAILABLE}
- reference_price numeric
- reference_timestamp
- pct_change computed relative to reference, or pct_change=None plus data_quality_flags when missing.

1.c Make RVOL session-aware and label it. If baseline not available, set RVOL=None and add data_quality_flags.

1.d Add/standardize `data_quality_flags` list in scanner payload (NO_MARKET_DATA, STALE_SNAPSHOT, HALTED, SSR, WIDE_SPREAD, LOW_LIQUIDITY, MISSING_FLOAT, MISSING_NEWS, MISSING_REFERENCE_PRICE, OTC_OR_INELIGIBLE, etc.).

1.e Ensure scanner payload is strategy-compatible facts (no decisions). Ensure orchestrator passes scanner facts through unchanged to strategy policy.

1.f CLOSED weekend prep: when session_label=CLOSED, system must still produce prep-ready output tagged for next tradable session (typically Monday PRE). Reference is last RTH close (Friday close).

After implementing Step 1, run all commands in `06_MANDATORY_VERIFICATION_COMMANDS.md` sections 1–4 for scanner-related items. Fix until PASS.

================================================================================
STEP 2 — PAPER TRADING + VERIFICATION (AUTHORITATIVE)
================================================================================
2.a Introduce/ensure `ExecutionProvider` abstraction. Implement:
- PaperExecutionProvider (PAPER)
- IBKRExecutionProvider (LIVE)
- LIVE_READ_ONLY provider that hard-blocks place_order.

2.b PaperExecutionProvider must be deterministic (seeded). Simulate fills (market and limit), partial fills (configurable), commissions, latency/slippage (configurable).

2.c Ensure PAPER updates the same DB schema/tables as LIVE; tag with execution_mode, no separate schema.

2.d Implement risk profile resolution and enforcement at the intent→order boundary:
- Load profile by name from config/env
- Validate profile exists in `src/config/risk_profiles.py`
- Clamp shares and enforce scaling rules (MICRO=1 share; no adds)
- Enforce daily limits and hard-stops requirement

2.e Add a deterministic verification harness CLI that can run scenarios:
- closed_weekend_prep
- pre_session_scan
- rth_trade_lifecycle
- micro_profile_trade

After implementing Step 2, run all commands in `06_MANDATORY_VERIFICATION_COMMANDS.md` sections 1–5. Fix until PASS.

================================================================================
STEP 3 — COMPLETE ROSS SETUPS (NO OMISSIONS)
================================================================================
3.a Use the user catalogue `SETUP_FAMILIES_AND_PATTERNS.md` as source of truth. Implement ALL listed setup families and micro triggers in Ross strategy policy/modules.

3.b Each intent must be traceable in logs/DB:
- setup_family_name
- micro_trigger_name
- key levels used

3.c Implement veto states:
- Parabolic exhaustion exit/stop-trading
- “Big red volume bigger than green” pause entries
- Topping-tail warnings (pause adds)

3.d Add verification script `src/verification/verify_ross_setups_complete.py` that enumerates implemented setups and fails if any are missing.

After implementing Step 3, run all commands in `06_MANDATORY_VERIFICATION_COMMANDS.md` including the Ross completeness check. Fix until PASS.

================================================================================
STOP CONDITION
================================================================================
Do not stop until:
- Step 1 PASS
- Step 2 PASS
- Step 3 PASS
AND all mandatory verification commands pass.

END OF INSTRUCTIONS.
END
