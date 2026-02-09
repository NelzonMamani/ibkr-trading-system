# M2 — ENFORCED INVARIANTS

- Contract IDs must be unique and start with `C_`.
- owner_component must be one of: core_engine, scanner, market_data, data,
  patterns, signals, strategies, risk, execution, brokers, storage, metadata.
- applies_to_modes must be a subset of {SIM, PAPER, READ_ONLY, LIVE}.
- All paths referenced by implemented or partial contracts must exist.
- Declared-only contracts must point to catalogue documentation paths.

END
