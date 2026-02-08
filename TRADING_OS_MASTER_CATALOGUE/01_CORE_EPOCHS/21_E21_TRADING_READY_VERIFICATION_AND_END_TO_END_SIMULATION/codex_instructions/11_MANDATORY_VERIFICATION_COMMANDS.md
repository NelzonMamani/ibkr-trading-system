# 11_MANDATORY_VERIFICATION_COMMANDS

Codex MUST run and record:

- python -m compileall src
- pytest (foundation + harness tests)
- SIM verification suite
- PAPER smoke suite (manual confirmation allowed)
- READ_ONLY safety suite

If any command fails, STOP and report.
