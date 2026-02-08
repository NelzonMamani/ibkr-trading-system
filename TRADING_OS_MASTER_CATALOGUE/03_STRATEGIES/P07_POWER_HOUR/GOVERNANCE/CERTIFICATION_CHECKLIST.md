# P07_POWER_HOUR — CERTIFICATION CHECKLIST (E19/E21)
**Timestamp:** 2026-02-08T01:28:21Z

- [ ] Strategy exists under src/strategies/<name>/ with E19 interface compliance
- [ ] strategy_policy.py includes full tunables + mapping tables (SF→XL, SF→K, SF→INV)
- [ ] REQUIRED C_* and REQUIRED K_* enforced
- [ ] Unit tests (pure strategy) pass
- [ ] E21 SIM run passes
- [ ] E21 PAPER run passes (DB writes)
- [ ] READ_ONLY run passes (no orders)
- [ ] LIVE safety validated (execution authority, risk veto)

END
