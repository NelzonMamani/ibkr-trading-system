# PR1044 Bounded READ_ONLY Observation Scope

## Scope

PR1044 keeps the PR1040 real READ_ONLY runtime observation adapter bounded. It does not complete PAPER readiness, does not enable PAPER or LIVE, does not allow broker order submission, cancellation, modification, preview submission, staging, flattening, reconciliation, or clean-start behavior, and does not relax Ross thresholds or catalyst, float, RVOL, price, or session gates.

This patch intentionally does not add a new analytics/storage proof path. Real analytics/storage write-readback evidence remains required before `READ_ONLY_OBSERVATION_VALID`, but PR1044 must not synthesize that proof and must not treat the observation JSON write/readback as storage evidence.

## Executive Verdict

PAPER_READY: NO
PAPER_READINESS_GATE: FAIL
PRODUCTION_TRADING_BEHAVIOR_CHANGED: NO
BROKER_ORDER_MUTATION_ALLOWED: NO
SYNTHETIC_ANALYTICS_STORAGE_PROOF_ALLOWED: NO
REAL_ANALYTICS_STORAGE_WRITE_READBACK_ADDED_BY_PR1044: NO
MARKET_DATA_DIAGNOSTIC_ADDED: YES

## Bounded Repairs

### Priced risk input

The adapter passes the numeric entry price parsed from the canonical Ross strategy entry model into the top-level `TradeIntentRecord.entry_price` field. That is the field consumed by `evaluate_trade_intents` for sizing, so READ_ONLY accepted setup evidence cannot rely only on metadata while bypassing the priced risk path.

Before calling the shared risk engine, the adapter builds a non-canonical READ_ONLY config account snapshot with a positive configured capital basis and `source=READ_ONLY_CONFIG`. The shared `src.risk.risk_audit` sizing behavior remains generic; it does not contain a PR1040 adapter-specific zero-capital exception.

Unknown zero-capital READ_ONLY account sources are still blocked by `INSUFFICIENT_CAPITAL_PER_SYMBOL`. The nonzero capital basis is scoped to PR1040 certification evidence, not general runtime risk approval.

If an accepted setup has no usable numeric entry price, PR1040 remains `READ_ONLY_OBSERVATION_INVALID` with:

`Accepted setup risk evidence missing numeric entry price.`

### Market data diagnostic

The adapter emits `market_data_diagnostic_artifact` from the scanner payload diagnostics. When scanner diagnostics explicitly report unavailable market data, the observation remains `INSUFFICIENT_EVIDENCE` with:

`Real market data diagnostic indicates scanner market data is unavailable.`

The diagnostic is evidence only. It does not relax scanner, catalyst, focus, pattern, strategy, risk, storage, broker, or execution gates.

### Storage evidence remains blocked unless real

PR1044 does not add SQLiteStore write/readback, does not set storage flags to true, and does not turn observation JSON output into analytics/storage proof. If no real storage source has already supplied `REAL_ANALYTICS_STORAGE_WRITE_READBACK`, the observation remains `INSUFFICIENT_EVIDENCE` with:

`Real analytics/storage write-readback evidence is unavailable.`

## Safety Posture

The patch preserves these PR1040 gates:

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

The adapter still emits a PR1039-compatible observation input at the configured observation-output path and can validate it through PR1039. A real no-trade observation remains acceptable only when all required evidence is complete and honest.

PAPER_READY remains NO.
PAPER_READINESS_GATE remains FAIL.
