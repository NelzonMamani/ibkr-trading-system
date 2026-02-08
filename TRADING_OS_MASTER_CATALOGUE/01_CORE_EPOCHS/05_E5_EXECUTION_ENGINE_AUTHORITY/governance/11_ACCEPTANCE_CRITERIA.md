# E5 — Acceptance Criteria

E5 is certified ONLY IF all are true:

- **Single execution authority**: orders cannot be submitted outside E5 in non-test runs.
- **Mode parity**: PAPER mirrors LIVE execution semantics (provider endpoint aside).
- **Read-only safety**: LIVE_READ_ONLY blocks execution with explicit reason codes.
- **Determinism**: SIM execution results are deterministic under replay.
- **Auditable outcomes**: every attempt emits trace data and produces an execution result.
- **No state corruption**: failures do not corrupt lifecycle or storage state.
