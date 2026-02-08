# P04 — Long Horizon Value — CERTIFICATION CHECKLIST (E19/E21)
**Catalogue path:** `03_STRATEGIES/P04_LONG_HORIZON_VALUE/GOVERNANCE/CERTIFICATION_CHECKLIST.md`  
**Timestamp:** 2026-02-08T01:09:09Z

## A) Canon coverage (NO PARTIALS)
- [ ] SF_* classified and mapped
- [ ] XL_* classified and mapped
- [ ] Required C_* enforced
- [ ] Required K_* enforced; optional mapped
- [ ] SCP/MCP utilisation declared (features only)
- [ ] Levels/Zones/INV declared

## B) Policy authority
- [ ] All tunables in `strategy_policy.py` (valuation bands, tranche sizing, cadence)
- [ ] No hidden constants

## C) Verification (mandatory)
- [ ] `python -m compileall src`
- [ ] `pytest -q`
- [ ] Strategy-local tests under `src/strategies/long_horizon_value/tests`
- [ ] E21 SIM multi-cycle run (daily/weekly simulation)
- [ ] PAPER run proves order submission via paper provider + DB writes
- [ ] READ_ONLY run emits intents but does not submit orders
- [ ] LIVE safety: respects execution authority; schedules when market closed

## D) Success criteria
- [ ] Deterministic tranche behaviour
- [ ] Allocation constraints enforced
- [ ] Clear audit trail for valuation/zone decisions
- [ ] No runtime errors

