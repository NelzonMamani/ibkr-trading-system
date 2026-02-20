# E25 Migration Plan (Executed)

## Step A — CLI correctness
- Hardened `src.cli.submit_one_order` for module invocation by adding argparse and delaying adapter imports to runtime execution path.
- Result: `python -m src.cli.submit_one_order --help` works without requiring optional IBKR adapter dependencies.

## Step B — Boundary shims
- No compatibility shims required for import path migrations in this pass.

## Step C — Move only if needed
- No large file/folder moves performed to preserve runtime stability.

## Step D — Git hygiene
- Updated `.gitignore` to ignore runtime-generated artifacts under `output/`, `logs/`, and generated data files (`*.db`, `*.sqlite`, `*.log`, `*.jsonl`).

## Verification checkpoints
- `python -m compileall src`
- `pytest -q`
- `python -m src.core_engine.orchestrator --mode READ_ONLY --cycles 1`
- `python -m src.core_engine.orchestrator --mode LIVE --cycles 1`
- `python -m src.core_engine.orchestrator --help`
- `python -m src.cli.submit_one_order --help`
