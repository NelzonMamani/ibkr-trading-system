# PHASE_05A_02_packaging_and_import_stabilisation

Date: 2026-01-15

## Objective
Eliminate import instability and enforce a single canonical “run from repo root” approach.

This phase exists because prior iterations suffered repeated `ModuleNotFoundError` and packaging confusion. Epoch 5 must prevent that class of failure.

## Inputs (Must Read)
- SYSTEM_TREE_AND_MODULE_MAP.md
- GLOBAL_FUNCTIONAL_REQUIREMENTS.md (standalone + integrated requirement)
- EPOCH_05_GOVERNANCE.md (Codex execution discipline)

## Rules
- Prefer `python -m <module>` execution from repository root.
- Do not introduce new package roots.
- Do not rename large directories unless strictly required.
- Add only the minimal `__init__.py` files required to make module imports deterministic.

## Allowed Files (Strict)
- pyproject.toml / setup.cfg (only if required)
- requirements*.txt (only if required)
- src/**/__init__.py (only as required to support imports)
- src/utils/validation.py (only if needed to support import checks)

## Tasks
1. Ensure a single import convention works for all modules:
   - orchestrator import paths
   - scanner import paths
   - strategy/pattern imports
2. Ensure running from root is stable:
   - `python -m src...` (or the repo’s canonical root) works consistently.
3. Ensure no “pip install core” style expectations exist (avoid naming collisions).

## Commands (Mandatory)
Run from repo root:
1. `python -c "import src"`
2. `python -c "import pkgutil; import src; print('OK: src import')"`

(If the repo’s canonical root is not `src`, replace accordingly; do not invent a second root.)

## Acceptance Checklist
- Both commands succeed without exceptions.
- No ambiguous relative imports remain in the touched scope.
- Import errors are eliminated for the core runtime path (orchestrator + scanner).

## Rollback Rule
If the fix requires touching more than init and minimal packaging config, stop and justify; do not refactor broadly.

END.
