# Mandatory Verification Commands

Codex MUST ensure all commands pass before stopping.

## Static checks
python -m compileall src/strategies/mean_reversion

## Unit tests
pytest src/strategies/mean_reversion

## Strategy dry-run (SIM)
python -m src.main --mode SIM --strategy mean_reversion --cycles 1

## Paper validation
python -m src.main --mode PAPER --strategy mean_reversion --cycles 1

## Live read-only validation
python -m src.main --mode LIVE_READ_ONLY --strategy mean_reversion --cycles 1

If any command fails:
→ Codex must fix and re-run.
