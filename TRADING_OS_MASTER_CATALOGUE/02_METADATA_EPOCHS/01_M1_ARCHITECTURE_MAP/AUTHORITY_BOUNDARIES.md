# M1 Authority Boundaries (Declaration)

## Final Authorities
- **Risk Engine (`src/risk/`)**: final authority on trade intents; may veto any intent.
- **Execution Engine (`src/execution/`)**: sole authority to submit/cancel orders.

## Non-Authoritative Modules
- **Scanner (`src/scanner/`)**: market discovery only; broker adapters are permitted only for market data connectivity and health checks (no orders).
- **Patterns (`src/patterns/`, `src/signals/`)**: pattern detection only.
- **Strategies (`src/strategies/`, `src/strategy/`)**: intent generation only.
- **Storage (`src/storage/`)**: persistence only.
- **Metadata & Verification (`TRADING_OS_MASTER_CATALOGUE/`, `verification_scripts/`, `src/tools/`)**: documentation and audit only.

## Broker Boundary
- **Broker Adapters (`src/broker/`, `src/brokers/`)** expose broker APIs to the execution engine only.
- No other subsystem may place orders or bypass execution.

END
