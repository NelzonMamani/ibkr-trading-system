# 04 — Evidence and Certification Updates

## Evidence files to produce
Create/update:
- `AUDIT_EVIDENCE/e24_async_runtime_report.json`
- `AUDIT_EVIDENCE/e24_async_import_chain_map.json`

## Report schema (minimum)
`e24_async_runtime_report.json` must include:
- `generated_at_utc`
- `python_version`
- `platform`
- `event_loop_policy`
- `had_loop_before`
- `created_loop`
- `set_loop_for_thread`
- `imports_tested` (list)
- `pytest_returncode` (if executed) OR `pytest_command_reference`

`e24_async_import_chain_map.json` must include:
- list of sensitive modules and whether they:
  - defer imports
  - route through compat wrapper
  - call ensure_event_loop before importing ib_insync/eventkit

## Certification updates
Update `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md` with an E24 entry:
- status and date
- evidence file paths

Also update any integrity report registries if your repo uses them (do not invent new registries).

