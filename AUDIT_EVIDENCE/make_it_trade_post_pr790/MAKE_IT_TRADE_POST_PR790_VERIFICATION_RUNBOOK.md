# Make It Trade Post-PR790 Verification Runbook

## Static validation

```bash
pytest -q tests/test_make_it_trade_pipeline_audit.py tests/test_trade_path_authority_model.py
pytest -q tests/test_p01_make_it_trade_layer.py tests/test_execution_pipeline_handoff_observability.py
```

## Pipeline validation

```bash
python -m src.cli.test_trade_pipeline --symbol AAPL --dry-run
```

Capture output to:

- `AUDIT_EVIDENCE/make_it_trade_post_pr790/pipeline_validation_dry_run.log`

## Readiness interpretation

Read `pipeline_validation_dry_run.log` for:

- strategy intents generated
- risk deny reason
- execution blocked reason
- session trade window status

## Callback-aware validation

Use `CALLBACK_PENDING` as the truthful terminal state whenever an order is submitted but no broker callback fill has arrived.

## One-command bundle

```bash
./tools/verify_make_it_trade_post_pr790.sh
```

This command regenerates:

- `pytest_trade_path_authority.txt`
- `pytest_pipeline_regression.txt`
- `pipeline_validation_dry_run.log`
- `verification_bundle.json`
