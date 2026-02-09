# CANONICAL MODES

The Trading OS supports exactly four canonical run modes, and only these modes
are considered authoritative for runtime semantics:

- SIM
- PAPER
- READ_ONLY
- LIVE

No other run modes are permitted. Risk configurations (e.g. LIVE_MICRO) are not
run modes and must normalize into one of the canonical modes above.

## Mode authority boundaries

- RUN_MODE_EFFECTIVE is the authoritative field for determining run mode.
- Any legacy or alias values MUST normalize into the canonical list.
- Subsystems must treat the canonical modes as immutable identifiers and must
  not create ad-hoc mode labels or implicit fallbacks.

END
