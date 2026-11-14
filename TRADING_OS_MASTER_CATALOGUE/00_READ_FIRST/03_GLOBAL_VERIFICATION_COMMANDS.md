# Global offline verification commands

Run from repository root with the effective project interpreter and dependencies.
Select affected tests before required final-head CI. For synthetic regression
checks use the existing hard transport guards:

```bash
PYTHONPATH=tests/offline:src:. python -m pytest -q <affected-test-paths>
```

See [RUNBOOK.md](../../RUNBOOK.md) for PowerShell environment handling and
current observation authority. Bare runtime, writable smoke commands and retired
root/console launchers are not baseline verification. Historical epoch command
lists and stored outputs remain evidence of their original scope, not current
instructions. Preserve original failures and proof limits.

PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.
