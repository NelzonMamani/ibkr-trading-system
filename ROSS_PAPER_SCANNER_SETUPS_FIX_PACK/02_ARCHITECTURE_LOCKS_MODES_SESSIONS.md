# 02_ARCHITECTURE_LOCKS_MODES_SESSIONS.md
TITLE: Authoritative Architecture Locks — Sessions vs Execution Modes vs Risk Profiles
DATE: 2026-01-31

## 1. Definitions (must not be conflated)

### 1.1 Sessions (market state) — external truth
Sessions are *not* a user configuration choice; they are derived from market hours and are mandatory:
- CLOSED (weekend/holiday)
- PRE
- RTH
- AH

All session handling must be consistent across scanner, strategy, and prep flows.

### 1.2 Execution modes — internal permission
Reduce to **exactly three** execution modes:
- PAPER
- LIVE_READ_ONLY
- LIVE

Remove or deprecate:
- SIM (dev-only; not used for readiness; ideally removed from CLI)
- LIVE_MICRO / LIVE_MICRO_SHARE (replace with risk profiles)

### 1.3 Risk profiles — orthogonal sizing constraints (config-only)
Risk profiles clamp/deny intents; they do not change strategy logic.
Start profiles:
- NORMAL
- MICRO (1 share / capped risk)
- SMALL (intermediate)

The user has already added:
- `src/config/risk_profiles.py` (authoritative profile definitions)

**Rule:** “MICRO trading” must be implemented as `RISK_PROFILE=MICRO` while `RUN_MODE=LIVE`, not as a separate execution mode.

## 2. Required config knobs (authoritative)
Codex must ensure there is a single, coherent runtime resolution for:
- `RUN_MODE` (PAPER | LIVE_READ_ONLY | LIVE)
- `RISK_PROFILE` (NORMAL | MICRO | SMALL | …)
- `ACTIVE_SESSIONS` (derived, not user-settable; user-set is advisory only)
- `EXECUTION_ENABLED` should not coexist as a separate safety switch that can silently disable trading. If it exists, it must be derived from RUN_MODE and cannot conflict.

## 3. Boot-time invariants (hard fails)
System must hard-fail at boot if:
- `RUN_MODE` is unknown
- `RISK_PROFILE` is unknown
- a “LIVE” mode is requested but execution provider is missing
- strategy is requested but not registered

## 4. Implementation constraints
- No strategy-specific logic in scanner.
- No mode-specific logic inside strategies.
- Risk profile enforcement occurs at the order-intent → order conversion boundary.

END
