# Mandatory Verification Commands

Codex must run these commands and record outputs (exit codes + summaries) into evidence JSON:

1. Compile
- `python -m compileall src`

2. Tests
- `pytest -q`

3. Smoke
- `python -m src.core_engine.orchestrator --mode READ_ONLY --cycles 1`
- `python -m src.core_engine.orchestrator --mode LIVE --cycles 1` (should not execute trades unless IBKR is connected; must not crash)

4. CLI sanity
- `python -m src.core_engine.orchestrator --help`
- `python -m src.cli.submit_one_order --help`

Note: IBKR connectivity failures are acceptable; import/runtime errors are not.
