# E27 Post-PR862 Paper Validation Runbook

## Purpose
Validate the authoritative execution truth lifecycle in PAPER mode after PR #862 quarantine:

`INTENT -> SUBMIT -> ACK -> FILL -> POSITION -> MANAGE -> EXIT -> CLOSE`

This runbook verifies that untracked `openOrder`/`orderStatus` callbacks remain quarantined and that fill/position/closure authority remains truthful.

## 1) Clean Environment Prep

1. Start from repo root:
   ```bash
   cd /workspace/ibkr-trading-system
   ```
2. Ensure no stale test mode override:
   ```bash
   unset EXECUTION_ENV
   ```
3. Ensure dependencies installed:
   ```bash
   pip install -r requirements.txt
   ```
4. Start IB Gateway or TWS paper session and confirm API access is enabled.

## 2) Required PAPER Environment Variables

Set at least:

```bash
export RUN_MODE=PAPER
export IBKR_READ_ONLY=false
export IBKR_KILL_SWITCH=false
export IBKR_HOST=127.0.0.1
export IBKR_PORT=7497
export IBKR_CLIENT_ID=101
```

Optional diagnostic visibility:

```bash
export EXECUTION_TRUTH_DIAGNOSTICS_MODE=1
export EXECUTION_TRUTH_DEGRADED_THRESHOLD=1
```

## 3) Validation Commands

### Unit validation (post-hardening assertions)
```bash
pytest -q src/tests/test_execution_truth_lifecycle_post_pr862.py src/tests/test_execution_safety_invariants.py
```

### Scripted lifecycle snapshot validation
```bash
python scripts/verify_execution_lifecycle_snapshot.py
```

### Paper smoke (controlled, with paper IBKR callback path)
```bash
bash scripts/run_paper_open_smoke_trade.sh
```

## 4) Logs to Inspect (Exact Families)

Check these log families in runtime output:

- `[EXECUTION][SUBMIT]`
- `[EXECUTION][ACK]`
- `[EXECUTION][FILL]`
- `[EXECUTION][POSITION]`
- `[EXECUTION][MANAGE]` (from management decision path if emitted by orchestrator loop)
- `[EXECUTION][EXIT]` (exit submission path)
- `[EXECUTION][CLOSE]` (terminal close/persist path)
- `[EXECUTION][TRACE]`
- `[EXECUTION][RECONCILE]`
- `[EXECUTION][TRUTH_GAP]`

Suggested grep sequence:

```bash
grep -E "\[EXECUTION\]\[(SUBMIT|ACK|FILL|POSITION|MANAGE|EXIT|CLOSE|TRACE|RECONCILE|TRUTH_GAP)\]" -n <runtime_log_file>
```

Also verify quarantine is intact:

```bash
grep -E "\[EXECUTION\]\[CALLBACK_IGNORED\].*reason=untracked_external_order" -n <runtime_log_file>
```

## 5) Success Criteria

A successful run shows:

1. `INTENT` reaches `SUBMIT` with stable `order_id` and trace ID.
2. `ACK` appears only for tracked orders.
3. `FILL` comes from authoritative callback path (`execDetails`) and dedupes duplicates.
4. `POSITION` becomes open deterministically after fill.
5. Management loop can evaluate and produce `EXIT` decisions for open positions.
6. Exit fills drive terminal `CLOSE`/closed lifecycle state.
7. Untracked `openOrder`/`orderStatus` are ignored and do not mutate lifecycle state.

## 6) Failure Signatures and Meaning

- `[EXECUTION][TRUTH_GAP] ... missing_order_id`: callback cannot be safely correlated.
- `[EXECUTION][RECONCILIATION_FAILED] ...`: callback/order reconciliation failed; inspect `order_ref` and mapping.
- `[EXECUTION][CALLBACK_IGNORED] ... untracked_external_order`: expected for external/manual orders; should not alter runtime state.
- `BROKER_TRUTH_NOT_CONFIRMED`: broker acknowledgement/visibility not established in strict path.
- repeated `BROKER_INACTIVE_UNKNOWN` while `OUTSIDE_RTH` warnings are present: indicates stale inactive classification behavior and requires review.

## 7) Operator Note

Do not accept any workaround that fabricates fills, positions, or exit closure. If callback truth is missing, treat as a truth-gap incident and investigate broker/session wiring.
