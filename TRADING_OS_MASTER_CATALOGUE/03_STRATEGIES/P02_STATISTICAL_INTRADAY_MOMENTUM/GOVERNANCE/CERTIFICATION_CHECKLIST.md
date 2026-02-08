# P02 — Statistical Intraday Momentum — CERTIFICATION CHECKLIST (E19/E21)
**Catalogue path:** `03_STRATEGIES/P02_STATISTICAL_INTRADAY_MOMENTUM/GOVERNANCE/CERTIFICATION_CHECKLIST.md`  
**Timestamp:** 2026-02-08T00:52:50Z

## A) Canon coverage (NO PARTIALS)
- [ ] All `SF_*` classified (ALLOWED/OPTIONAL/DENIED) and mapped to utilisation.
- [ ] All `XL_*` classified and mapped (SF→XL).
- [ ] Required `C_*` list implemented and enforced.
- [ ] Required `K_*` list implemented and enforced; optional K_* mapped per SF/mode.
- [ ] SCP_* and MCP_* utilisation declared (inputs only; no direct triggers).
- [ ] Required LVL/ZONE/INV utilisation declared.

## B) Policy tuning authority
- [ ] All behavioural thresholds exist as policy parameters (no hidden constants).
- [ ] Policy changes are reflected in decision artifacts.

## C) Verification (mandatory)
**Run commands (example; Codex must align to repo reality):**
- [ ] `python -m compileall src`
- [ ] `pytest -q`
- [ ] Strategy-local tests under `src/strategies/statistical_intraday_momentum/tests`
- [ ] E21 end-to-end simulation: scan → watchlist → focus → intents → (paper) execution → DB records
- [ ] Verify that READ_ONLY emits intents but does not execute orders
- [ ] Verify that LIVE respects EXECUTION_ENGINE_AUTHORITY and risk veto

## D) Success criteria
- [ ] Deterministic watchlist sizes (K and M)
- [ ] Deterministic intent cap per cycle (policy-controlled)
- [ ] Clear, auditable reasons for no-trade decisions
- [ ] No runtime errors across SIM/PAPER/READ_ONLY/LIVE

