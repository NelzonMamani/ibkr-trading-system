## Safety Invariants (Hard Laws)

1. No execution in LIVE_READ_ONLY
2. PAPER cannot exceed LIVE risk limits
3. SIM cannot mutate persistent state unless explicitly allowed
4. Mode switching mid-run is forbidden
5. All modes emit traceability artifacts
