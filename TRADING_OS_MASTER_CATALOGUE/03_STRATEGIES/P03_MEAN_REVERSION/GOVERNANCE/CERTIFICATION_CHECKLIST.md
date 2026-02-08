# P03 — Mean Reversion — CERTIFICATION CHECKLIST (E19/E21)
**Catalogue path:** `03_STRATEGIES/P03_MEAN_REVERSION/GOVERNANCE/CERTIFICATION_CHECKLIST.md`  
**Timestamp:** 2026-02-08T01:01:41Z

## A) Canon coverage (NO PARTIALS)
- [ ] SF_* classified and mapped; denied list explicit
- [ ] XL_* classified and mapped (SF→XL; denied entries explicit)
- [ ] Required C_* enforced
- [ ] Required K_* enforced; optional K_* mapped per SF/mode
- [ ] SCP/MCP utilisation declared (inputs only)
- [ ] LVL/ZONE/INV utilisation declared

## B) Policy authority
- [ ] All behaviour thresholds in `strategy_policy.py`
- [ ] No hidden constants in modules

## C) Verification (mandatory)
- [ ] `python -m compileall src`
- [ ] `pytest -q`
- [ ] Strategy-local tests under `src/strategies/mean_reversion/tests`
- [ ] E21 SIM run: scan→watchlist→focus→intents
- [ ] E21 PAPER run: intents→paper execution provider→DB writes
- [ ] READ_ONLY run: intents emitted, no orders
- [ ] LIVE safety: respects execution authority + risk veto (no unintended orders)

## D) Success criteria
- [ ] Deterministic decisions; clear no-trade reasons
- [ ] Mean distance extreme gating works
- [ ] Regime gating prevents fading strong trend days
- [ ] No runtime errors across modes

