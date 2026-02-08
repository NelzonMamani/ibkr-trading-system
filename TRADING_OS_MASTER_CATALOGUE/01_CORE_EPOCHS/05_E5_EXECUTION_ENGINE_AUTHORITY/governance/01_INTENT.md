# E5 — Intent

E5 exists to guarantee that execution is:
1) **Authoritative** (single engine owns all broker interaction)
2) **Mode-correct** (SIM/PAPER/LIVE_READ_ONLY/LIVE semantics are enforced)
3) **Risk-bound** (cannot exceed risk constraints; cannot execute without approval)
4) **Lifecycle-bound** (cannot violate position state machine; updates are consistent)
5) **Auditable** (every attempt is traceable with reason codes and IDs)

E5 is the boundary where the Trading OS stops "thinking" and starts "acting".
