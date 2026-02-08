# 03_REQUIRED_HARNESS_ARTIFACTS

Codex MUST implement a first-class verification harness with:

- CLI entrypoint (stable)
- Deterministic execution in SIM
- Artifact output directory (stable paths)
- Structured PASS/FAIL reporting

Minimum CLI contracts:
- python -m src.verify.e2e --mode SIM --scenario <name>
- python -m src.verify.e2e --mode PAPER --scenario smoke
- python -m src.verify.e2e --mode READ_ONLY --scenario smoke

All outputs must be machine-readable and human-readable.
