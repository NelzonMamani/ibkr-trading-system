# PR1043 Real READ_ONLY Observation Completion Repair

## Scope

PR1043 repairs the PR1040 real READ_ONLY runtime observation adapter completion path. It does not enable PAPER or LIVE, does not allow broker order submission, cancellation, modification, preview submission, staging, flattening, reconciliation, or clean-start behavior, and does not relax Ross thresholds or catalyst, float, RVOL, price, or session gates.

## Executive Verdict

PAPER_READY: NO
PAPER_READINESS_GATE: FAIL
PRODUCTION_TRADING_BEHAVIOR_CHANGED: NO
BROKER_ORDER_MUTATION_ALLOWED: NO
SYNTHETIC_ANALYTICS_STORAGE_PROOF_ALLOWED: NO

## Repairs

### Real analytics/storage proof

PR1040 no longer needs to remain incomplete solely because analytics/storage proof is unavailable. The adapter now writes real runtime analytics evidence through the existing `src.storage.sqlite_store.SQLiteStore` layer and reads it back before marking storage evidence verified.

The proof writes:

- `runs`
- `cycles`
- `trade_records`
- `cycle_summary_rows`

The proof reads back:

- `trade_records`
- `cycle_summary_rows`

The PR1040 observation JSON write/readback is still not considered analytics/storage proof. Storage evidence is valid only when the adapter records source `REAL_ANALYTICS_STORAGE_WRITE_READBACK` after a successful SQLiteStore write/readback match.

If the SQLiteStore write/readback is unavailable or mismatched, the adapter keeps storage evidence unavailable and classification remains `INSUFFICIENT_EVIDENCE` with:

`Real analytics/storage write-readback evidence is unavailable.`

### Priced risk input

The adapter now passes the numeric entry price parsed from the canonical Ross strategy entry model into the top-level `TradeIntentRecord.entry_price` field. That is the field consumed by `evaluate_trade_intents` for sizing, so READ_ONLY accepted setup evidence cannot rely only on metadata while bypassing the priced risk path.

PR1044 keeps that priced sizing path from becoming a zero-capital false negative: when the PR1040 adapter supplies its READ_ONLY certification account source with no broker capital, risk sizing uses the configured READ_ONLY capital basis and records `capital_source=READ_ONLY_CONFIG`. This remains non-canonical certification evidence only; it does not enable PAPER or LIVE and does not mutate broker orders.

Unknown zero-capital READ_ONLY account sources are still blocked by `INSUFFICIENT_CAPITAL_PER_SYMBOL`. The nonzero fallback is scoped to PR1040 certification evidence, not general runtime risk approval.

If an accepted setup has no usable numeric entry price, PR1040 remains `READ_ONLY_OBSERVATION_INVALID` with:

`Accepted setup risk evidence missing numeric entry price.`

## Safety Posture

The repair preserves these PR1040 gates:

- READ_ONLY only
- execution disabled
- zero broker order mutations
- no manual focus readiness proof
- no synthetic trade intent
- no fake accepted setup
- accepted setup must come from `RossMomentumStrategy.evaluate`
- accepted setup requires focused symbol, confirmed catalyst, real pattern input evidence, target model, priced intent, READ_ONLY risk decision, execution disabled, zero broker mutation, and real storage proof
- no-trade observation can pass only with complete scanner, catalyst/news, focus, pattern, decision, broker audit, and storage evidence

## Operator Note

The default storage database is:

`artifacts/certification/pr1040/analytics_storage/read_only_runtime_observation.sqlite3`

Operators may override it with `PR1040_ANALYTICS_STORAGE_DB` when needed. The adapter still emits a PR1039-compatible observation input at the configured observation-output path and can validate it through PR1039.

PAPER_READY remains NO.
PAPER_READINESS_GATE remains FAIL.
