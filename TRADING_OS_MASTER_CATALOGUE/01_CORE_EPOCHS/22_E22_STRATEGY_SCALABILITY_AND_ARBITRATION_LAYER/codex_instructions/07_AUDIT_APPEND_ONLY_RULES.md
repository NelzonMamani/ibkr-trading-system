
# 07_AUDIT_APPEND_ONLY_RULES — E22

- Do not delete prior audit evidence.
- E22 verifier may overwrite its own epoch directory when run with `--allow-overwrite`.
- Any changes to SYSTEM_STATE_CERTIFIED.md must be explicit and traceable:
  - only set E22 to CERTIFIED when verifier passes and certification_verdict says CERTIFIED
