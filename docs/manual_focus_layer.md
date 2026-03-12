# Manual Focus Layer

## Purpose
The Manual Focus Layer lets an operator inject up to 5 symbols directly into the focus stage.
It bypasses **scanner discovery only** and still runs through normal hydration, pattern, risk, and execution flow.

## Configuration
File: `config/manual_focus.json`

Default template:

```json
{
  "enabled": true,
  "manual_focus": ["TMDE", "HURA", "CYN", "OCGN"],
  "max_manual_symbols": 5,
  "live_reload_seconds": 60
}
```

Behavior:
- `enabled=false` disables manual focus.
- `manual_focus` can be empty.
- symbols are normalized to uppercase.
- duplicates are removed.
- `max_manual_symbols` hard-caps manual list.

## Live Reload
The orchestrator reloads manual focus config on an interval controlled by `live_reload_seconds`.
When symbols change, logs show:

- `[MANUAL_FOCUS] update_detected symbols=[...]`
- `[FOCUS][MANUAL] symbol=...`
- `[FOCUS][MERGED] scanner_focus=... manual_focus=... active_focus=...`
- `[FOCUS][ACTIVE] symbols=[...]`

## Ross strategy integration
Manual symbols are merged into scanner watchlist/focus candidates and flow through the same strategy stack:
- data hydration
- pattern evaluation
- risk checks
- execution routing

No strategy gates are bypassed.

## Troubleshooting
- If `config/manual_focus.json` is missing, it is auto-recreated and logs:
  - `[MANUAL_FOCUS] config_missing_recreated`
- If JSON is malformed, loader logs warning and returns empty focus.
- Run verification helper:

```bash
python verification_scripts/verify_manual_focus.py
```
