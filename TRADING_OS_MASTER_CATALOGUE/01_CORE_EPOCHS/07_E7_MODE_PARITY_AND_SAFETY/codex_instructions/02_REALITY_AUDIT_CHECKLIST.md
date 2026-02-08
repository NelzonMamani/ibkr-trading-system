# Reality Audit Checklist — E7

Inspect the repository and answer YES/NO with evidence:

1. Is run mode resolved once at bootstrap?
2. Can run mode change mid-run? (Must be NO)
3. Are SIM/PAPER/LIVE code paths identical except providers?
4. Is LIVE_READ_ONLY execution blocked at the final authority?
5. Do PAPER and LIVE enforce identical risk limits?
6. Are all subsystems consuming the same resolved mode?
7. Are there hidden feature flags altering behavior per mode?
8. Are trace events stamped with run_mode consistently?
9. Do smoke scripts exercise all modes?

Produce a short audit summary.
