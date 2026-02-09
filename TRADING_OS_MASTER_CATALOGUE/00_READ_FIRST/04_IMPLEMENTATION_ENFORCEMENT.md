# Implementation Enforcement Rule (Authoritative)

If an epoch audit results in a ❌ or ◐ status for any required capability:

- Codex MUST implement the missing or non-canonical capability
- Codex MUST refactor existing code if required to satisfy governance
- Codex MUST NOT stop after audit alone
- Codex MUST continue implementation → verification → re-audit
- Codex MAY NOT proceed to the next epoch until the current epoch is CERTIFIED

Audit-only epochs are forbidden unless explicitly authorised by human instruction.

END
