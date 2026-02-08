# E18 — SUCCESS CRITERIA (BINARY)

E18 is complete when:

1) All governance checklists are implemented and registered:
- SF_* list complete
- XL_* list complete
- C_* list complete
- K_* list complete
- Candlestick layer 1/2/3 complete
- Levels/zones model present with availability flags
- Structure state vocabulary implemented
- Invalidation contract implemented

2) Strategy policy primacy is preserved:
- No global Ross-only gates
- Simple strategies remain viable
- Specialized strategies are not diluted

3) Symbol commitment hydration works:
- Daily/hourly/1m bars fetched for committed symbols ASAP
- Derived series computed as data
- HAS_NEWS boolean available
- completeness flags present

4) Data lifecycle/reset works:
- soft/hard/version reset available
- caches regenerable
- safe degradation after reset

5) Translation/coverage/drift reports exist for all strategies and are deterministic.

6) Tests and verification pass (see mandatory verification commands).

If any checklist item is missing or any proof fails => E18 FAIL.

END
