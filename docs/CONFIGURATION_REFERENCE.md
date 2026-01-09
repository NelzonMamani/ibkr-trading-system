# Configuration Reference

Generated from `src/config/config_registry.py`.

## CLI

### IBKR_CLIENT_ID_ORDER_SUBMIT

* **Type:** <class 'int'>
* **Default:** `9012`
* **Env overrides:** `IBKR_CLIENT_ID_ORDER_SUBMIT`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** IBKR client ID for order submission connections.

### IBKR_GUARD_PERSIST_PATH

* **Type:** <class 'str'>
* **Default:** `runtime/submission_guard.json`
* **Env overrides:** `IBKR_GUARD_PERSIST_PATH`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Persistence path for the submission guard state.

### IBKR_KILL_SWITCH

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `IBKR_KILL_SWITCH`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Global kill switch to block submissions.

### IBKR_MAX_ORDERS_PER_RUN

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `IBKR_MAX_ORDERS_PER_RUN`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Maximum IBKR orders allowed per run.

### IBKR_ORDER_SUBMISSION_ENABLED

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `IBKR_ORDER_SUBMISSION_ENABLED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Enable IBKR order submission for live/paper.

### IBKR_ORDER_TRANSLATION_ENABLED

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `IBKR_ORDER_TRANSLATION_ENABLED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Enable IBKR order translation.

### IBKR_PAPER_ONLY_ENFORCED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `IBKR_PAPER_ONLY_ENFORCED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Enforce paper-only routing where applicable.

### IBKR_TRANSLATION_TEST_CLIENT_ORDER_ID

* **Type:** <class 'str'>
* **Default:** `dry-run-ibkr-translation`
* **Env overrides:** `IBKR_TRANSLATION_TEST_CLIENT_ORDER_ID`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Client order ID for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_DIRECTION

* **Type:** <class 'str'>
* **Default:** `LONG`
* **Env overrides:** `IBKR_TRANSLATION_TEST_DIRECTION`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Direction for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_LIMIT_PRICE

* **Type:** <class 'float'>
* **Default:** `None`
* **Env overrides:** `IBKR_TRANSLATION_TEST_LIMIT_PRICE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Limit price for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_ORDER_TYPE

* **Type:** <class 'str'>
* **Default:** `MKT`
* **Env overrides:** `IBKR_TRANSLATION_TEST_ORDER_TYPE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Order type for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_QUANTITY

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `IBKR_TRANSLATION_TEST_QUANTITY`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Quantity for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_STRATEGY_NAME

* **Type:** <class 'str'>
* **Default:** `DRY_RUN`
* **Env overrides:** `IBKR_TRANSLATION_TEST_STRATEGY_NAME`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Strategy name for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_SYMBOL

* **Type:** <class 'str'>
* **Default:** ``
* **Env overrides:** `IBKR_TRANSLATION_TEST_SYMBOL`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Optional symbol for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_TIF

* **Type:** <class 'str'>
* **Default:** `DAY`
* **Env overrides:** `IBKR_TRANSLATION_TEST_TIF`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Time-in-force for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_TRADER_TYPE

* **Type:** <class 'str'>
* **Default:** `MANUAL`
* **Env overrides:** `IBKR_TRANSLATION_TEST_TRADER_TYPE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Trader type for IBKR translation dry-run.

## CoreOrchestrator

### ACTIVE_SESSIONS

* **Type:** <class 'list'>
* **Default:** `["PRE", "REGULAR", "AFTER"]`
* **Env overrides:** `ACTIVE_SESSIONS`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Market sessions considered active for safety checks.

### CYCLE_SLEEP_SECONDS

* **Type:** <class 'int'>
* **Default:** `3`
* **Env overrides:** `CYCLE_SLEEP_SECONDS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Sleep interval between orchestrator cycles.

### EVENT_REPLAY_MODE

* **Type:** <class 'str'>
* **Default:** `CYCLE`
* **Env overrides:** `EVENT_REPLAY_MODE`
* **Enforcement:** SOFT
* **Mutable:** static
* **Choices:** ['OFF', 'CYCLE', 'RUN']
* **Description:** Requested event replay mode before live safety overrides.

### EVENT_REPLAY_MODE_EFFECTIVE

* **Type:** <class 'str'>
* **Default:** `None`
* **Env overrides:** `(none)`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['OFF', 'CYCLE', 'RUN']
* **Description:** Derived event replay mode (forced OFF in live modes).

### EXECUTION_ENABLED

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `EXECUTION_ENABLED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Master execution enable flag (only honored in LIVE_MICRO).

### EXECUTION_ENABLED_EFFECTIVE

* **Type:** <class 'bool'>
* **Default:** `None`
* **Env overrides:** `(none)`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Derived execution enable flag after run-mode safety rules.

### IBKR_API_WRITE_ALLOWED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `IBKR_API_WRITE_ALLOWED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Allow write access to IBKR API (used for live read-only override).

### INTENT_DEDUP_SELFTEST_ENABLED

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `INTENT_DEDUP_SELFTEST_ENABLED`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Enable self-test to deduplicate intents during normalization.

### LIVE_MICRO_DAILY_MAX_LOSS

* **Type:** <class 'float'>
* **Default:** `5.0`
* **Env overrides:** `LIVE_MICRO_DAILY_MAX_LOSS`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Daily loss circuit breaker (absolute value).

### LIVE_MICRO_MAX_CONCURRENT_TRADES

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `LIVE_MICRO_MAX_CONCURRENT_TRADES`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Max concurrent trades allowed in LIVE_MICRO.

### LIVE_MICRO_MAX_CONSECUTIVE_LOSSES

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `LIVE_MICRO_MAX_CONSECUTIVE_LOSSES`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Max consecutive losses before halting LIVE_MICRO.

### LIVE_MICRO_MAX_TRADES_PER_DAY

* **Type:** <class 'int'>
* **Default:** `3`
* **Env overrides:** `LIVE_MICRO_MAX_TRADES_PER_DAY`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Max total trades allowed per day in LIVE_MICRO.

### RUN_MODE

* **Type:** <class 'str'>
* **Default:** `SIM`
* **Env overrides:** `RUN_MODE`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['SIM', 'PAPER', 'LIVE', 'LIVE_READ_ONLY', 'LIVE_MICRO']
* **Description:** Baseline runtime mode before safety-derived overrides.

### RUN_MODE_EFFECTIVE

* **Type:** <class 'str'>
* **Default:** `None`
* **Env overrides:** `(none)`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['SIM', 'PAPER', 'LIVE', 'LIVE_READ_ONLY', 'LIVE_MICRO']
* **Description:** Derived run mode after safety rules (LIVE_READ_ONLY override).

### SCANNER_MODE

* **Type:** <class 'str'>
* **Default:** `TEACHING`
* **Env overrides:** `SCANNER_MODE`
* **Enforcement:** SOFT
* **Mutable:** static
* **Choices:** ['TEACHING', 'LIVE_READONLY']
* **Description:** Scanner selection mode (TEACHING/LIVE_READONLY).

## ExecutionEngine

### EXECUTION_ENABLED

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `EXECUTION_ENABLED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Master execution enable flag (only honored in LIVE_MICRO).

### EXECUTION_ENABLED_EFFECTIVE

* **Type:** <class 'bool'>
* **Default:** `None`
* **Env overrides:** `(none)`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Derived execution enable flag after run-mode safety rules.

### EXECUTION_MAX_ATTEMPTS_BY_TRADER

* **Type:** <class 'dict'>
* **Default:** `{"SCALPER": 2, "MOMENTUM": 3, "DEFAULT": 1}`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Max execution attempts per trader type.

### FUTURE_EXECUTION_RATE_LIMIT

* **Type:** <class 'int'>
* **Default:** `0`
* **Env overrides:** `FUTURE_EXECUTION_RATE_LIMIT`
* **Enforcement:** ADVISORY
* **Mutable:** dynamic
* **Description:** PLACEHOLDER: per-minute execution rate limit.

### IBKR_ACK_TIMEOUT_SECONDS

* **Type:** <class 'int'>
* **Default:** `10`
* **Env overrides:** `IBKR_ACK_TIMEOUT_SECONDS`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Timeout for IBKR submission acknowledgements.

### IBKR_DEFAULT_CURRENCY

* **Type:** <class 'str'>
* **Default:** `USD`
* **Env overrides:** `IBKR_DEFAULT_CURRENCY`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Default currency for IBKR order translation.

### IBKR_DEFAULT_EXCHANGE

* **Type:** <class 'str'>
* **Default:** `SMART`
* **Env overrides:** `IBKR_DEFAULT_EXCHANGE`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Default exchange for IBKR order translation.

### IBKR_GUARD_PERSIST_PATH

* **Type:** <class 'str'>
* **Default:** `runtime/submission_guard.json`
* **Env overrides:** `IBKR_GUARD_PERSIST_PATH`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Persistence path for the submission guard state.

### IBKR_KILL_SWITCH

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `IBKR_KILL_SWITCH`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Global kill switch to block submissions.

### IBKR_MAX_ORDERS_PER_RUN

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `IBKR_MAX_ORDERS_PER_RUN`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Maximum IBKR orders allowed per run.

### IBKR_ORDER_SUBMISSION_ENABLED

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `IBKR_ORDER_SUBMISSION_ENABLED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Enable IBKR order submission for live/paper.

### IBKR_ORDER_TRANSLATION_ENABLED

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `IBKR_ORDER_TRANSLATION_ENABLED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Enable IBKR order translation.

### IBKR_READONLY_ENABLED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `IBKR_READONLY_ENABLED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** If true, IBKR order routing is blocked system-wide.

### IBKR_SUBMIT_ONLY_SYMBOL

* **Type:** <class 'str'>
* **Default:** `None`
* **Env overrides:** `IBKR_SUBMIT_ONLY_SYMBOL`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** If set, only allow submissions for this symbol.

### LIVE_MICRO_MAX_CONCURRENT_TRADES

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `LIVE_MICRO_MAX_CONCURRENT_TRADES`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Max concurrent trades allowed in LIVE_MICRO.

### LIVE_MICRO_REQUIRED_QUANTITY

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `(none)`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Required order quantity for LIVE_MICRO submissions.

### RISK_MAX_POSITION_SIZE

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `(none)`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Max position size allowed by RiskEngine.

### RUN_MODE

* **Type:** <class 'str'>
* **Default:** `SIM`
* **Env overrides:** `RUN_MODE`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['SIM', 'PAPER', 'LIVE', 'LIVE_READ_ONLY', 'LIVE_MICRO']
* **Description:** Baseline runtime mode before safety-derived overrides.

### RUN_MODE_EFFECTIVE

* **Type:** <class 'str'>
* **Default:** `None`
* **Env overrides:** `(none)`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['SIM', 'PAPER', 'LIVE', 'LIVE_READ_ONLY', 'LIVE_MICRO']
* **Description:** Derived run mode after safety rules (LIVE_READ_ONLY override).

## IBKR

### IBKR_ACK_TIMEOUT_SECONDS

* **Type:** <class 'int'>
* **Default:** `10`
* **Env overrides:** `IBKR_ACK_TIMEOUT_SECONDS`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Timeout for IBKR submission acknowledgements.

### IBKR_API_WRITE_ALLOWED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `IBKR_API_WRITE_ALLOWED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Allow write access to IBKR API (used for live read-only override).

### IBKR_CLIENT_ID

* **Type:** <class 'int'>
* **Default:** `7`
* **Env overrides:** `IBKR_CLIENT_ID`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** IBKR client ID for market data connections.

### IBKR_CLIENT_ID_ORDER_SUBMIT

* **Type:** <class 'int'>
* **Default:** `9012`
* **Env overrides:** `IBKR_CLIENT_ID_ORDER_SUBMIT`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** IBKR client ID for order submission connections.

### IBKR_DEFAULT_CURRENCY

* **Type:** <class 'str'>
* **Default:** `USD`
* **Env overrides:** `IBKR_DEFAULT_CURRENCY`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Default currency for IBKR order translation.

### IBKR_DEFAULT_EXCHANGE

* **Type:** <class 'str'>
* **Default:** `SMART`
* **Env overrides:** `IBKR_DEFAULT_EXCHANGE`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Default exchange for IBKR order translation.

### IBKR_HOST

* **Type:** <class 'str'>
* **Default:** `127.0.0.1`
* **Env overrides:** `IBKR_HOST`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** IBKR gateway host.

### IBKR_LIVE_PORT

* **Type:** <class 'int'>
* **Default:** `7496`
* **Env overrides:** `IBKR_LIVE_PORT`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Live trading port for IBKR order submission.

### IBKR_PAPER_HOST

* **Type:** <class 'str'>
* **Default:** `127.0.0.1`
* **Env overrides:** `IBKR_PAPER_HOST`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Paper trading host for IBKR order submission.

### IBKR_PAPER_ONLY_ENFORCED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `IBKR_PAPER_ONLY_ENFORCED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Enforce paper-only routing where applicable.

### IBKR_PAPER_PORT

* **Type:** <class 'int'>
* **Default:** `7497`
* **Env overrides:** `IBKR_PAPER_PORT`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Paper trading port for IBKR order submission.

### IBKR_PORT

* **Type:** <class 'int'>
* **Default:** `7497`
* **Env overrides:** `IBKR_PORT`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** IBKR gateway port.

### IBKR_READONLY_ENABLED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `IBKR_READONLY_ENABLED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** If true, IBKR order routing is blocked system-wide.

### IBKR_SNAPSHOT_TIMEOUT_SECONDS

* **Type:** <class 'int'>
* **Default:** `5`
* **Env overrides:** `IBKR_SNAPSHOT_TIMEOUT_SECONDS`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Timeout for IBKR snapshot requests in seconds.

## LiveReadOnlyScanner

### IBKR_AUTO_LOCKDOWN_ENABLED

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `IBKR_AUTO_LOCKDOWN_ENABLED`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Enable automatic lockdown when data quality fails.

### IBKR_FALLBACK_ENABLED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `IBKR_FALLBACK_ENABLED`
* **Enforcement:** SOFT
* **Mutable:** per-cycle
* **Description:** Allow fallback scanner outputs when IBKR data is unavailable.

### IBKR_MAX_SYMBOLS_PER_CYCLE

* **Type:** <class 'int'>
* **Default:** `50`
* **Env overrides:** `IBKR_MAX_SYMBOLS_PER_CYCLE`
* **Enforcement:** HARD
* **Mutable:** per-cycle
* **Description:** Upper bound on symbols that may be snapshotted per cycle.

### IBKR_SNAPSHOT_MAX_AGE_SECONDS

* **Type:** <class 'int'>
* **Default:** `15`
* **Env overrides:** `IBKR_SNAPSHOT_MAX_AGE_SECONDS`
* **Enforcement:** SOFT
* **Mutable:** per-cycle
* **Description:** Maximum age of IBKR snapshot data before treated as stale.

### SCANNER_DEFAULT_SYMBOLS

* **Type:** <class 'list'>
* **Default:** `["AAPL", "TSLA", "NVDA", "AMD", "SPY"]`
* **Env overrides:** `(none)`
* **Enforcement:** ADVISORY
* **Mutable:** static
* **Description:** Fallback symbol set when SCANNER_SYMBOLS is empty.

### SCANNER_SESSION_WINDOWS_UTC

* **Type:** <class 'dict'>
* **Default:** `{"PRE_START": 12.0, "RTH_START": 14.0, "AFT_START": 21.5, "AFT_END": 23.0}`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** UTC hour windows for scanner session labels.

### SCANNER_SYMBOLS

* **Type:** <class 'list'>
* **Default:** `[]`
* **Env overrides:** `SCANNER_SYMBOLS, IBKR_SCAN_SYMBOLS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Explicit scanner symbol list (comma-separated).

## Main

### IBKR_SMOKE_SYMBOL

* **Type:** <class 'str'>
* **Default:** ``
* **Env overrides:** `IBKR_SMOKE_SYMBOL`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Symbol for IBKR read-only smoke test.

### IBKR_TRANSLATION_TEST_CLIENT_ORDER_ID

* **Type:** <class 'str'>
* **Default:** `dry-run-ibkr-translation`
* **Env overrides:** `IBKR_TRANSLATION_TEST_CLIENT_ORDER_ID`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Client order ID for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_DIRECTION

* **Type:** <class 'str'>
* **Default:** `LONG`
* **Env overrides:** `IBKR_TRANSLATION_TEST_DIRECTION`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Direction for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_LIMIT_PRICE

* **Type:** <class 'float'>
* **Default:** `None`
* **Env overrides:** `IBKR_TRANSLATION_TEST_LIMIT_PRICE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Limit price for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_ORDER_TYPE

* **Type:** <class 'str'>
* **Default:** `MKT`
* **Env overrides:** `IBKR_TRANSLATION_TEST_ORDER_TYPE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Order type for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_QUANTITY

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `IBKR_TRANSLATION_TEST_QUANTITY`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Quantity for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_STRATEGY_NAME

* **Type:** <class 'str'>
* **Default:** `DRY_RUN`
* **Env overrides:** `IBKR_TRANSLATION_TEST_STRATEGY_NAME`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Strategy name for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_SYMBOL

* **Type:** <class 'str'>
* **Default:** ``
* **Env overrides:** `IBKR_TRANSLATION_TEST_SYMBOL`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Optional symbol for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_TIF

* **Type:** <class 'str'>
* **Default:** `DAY`
* **Env overrides:** `IBKR_TRANSLATION_TEST_TIF`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Time-in-force for IBKR translation dry-run.

### IBKR_TRANSLATION_TEST_TRADER_TYPE

* **Type:** <class 'str'>
* **Default:** `MANUAL`
* **Env overrides:** `IBKR_TRANSLATION_TEST_TRADER_TYPE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Trader type for IBKR translation dry-run.

## MarketDataHub

### IBKR_CLIENT_ID

* **Type:** <class 'int'>
* **Default:** `7`
* **Env overrides:** `IBKR_CLIENT_ID`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** IBKR client ID for market data connections.

### IBKR_FALLBACK_SOURCE

* **Type:** <class 'str'>
* **Default:** `STATIC`
* **Env overrides:** `IBKR_FALLBACK_SOURCE`
* **Enforcement:** SOFT
* **Mutable:** per-cycle
* **Description:** Label for fallback data source when IBKR unavailable.

### IBKR_HOST

* **Type:** <class 'str'>
* **Default:** `127.0.0.1`
* **Env overrides:** `IBKR_HOST`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** IBKR gateway host.

### IBKR_MARKET_DATA_TYPE

* **Type:** <class 'str'>
* **Default:** `LIVE`
* **Env overrides:** `IBKR_MARKET_DATA_TYPE`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['LIVE', 'DELAYED', 'DELAYED_FROZEN', 'FROZEN']
* **Description:** IBKR market data type (LIVE/DELAYED/etc).

### IBKR_MAX_SYMBOLS_PER_CYCLE

* **Type:** <class 'int'>
* **Default:** `50`
* **Env overrides:** `IBKR_MAX_SYMBOLS_PER_CYCLE`
* **Enforcement:** HARD
* **Mutable:** per-cycle
* **Description:** Upper bound on symbols that may be snapshotted per cycle.

### IBKR_PORT

* **Type:** <class 'int'>
* **Default:** `7497`
* **Env overrides:** `IBKR_PORT`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** IBKR gateway port.

### IBKR_READONLY_ENABLED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `IBKR_READONLY_ENABLED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** If true, IBKR order routing is blocked system-wide.

### IBKR_SNAPSHOT_TIMEOUT_SECONDS

* **Type:** <class 'int'>
* **Default:** `5`
* **Env overrides:** `IBKR_SNAPSHOT_TIMEOUT_SECONDS`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Timeout for IBKR snapshot requests in seconds.

## NewsEngine

### FUTURE_NEWS_SENTIMENT_MODEL

* **Type:** <class 'str'>
* **Default:** `PLACEHOLDER`
* **Env overrides:** `FUTURE_NEWS_SENTIMENT_MODEL`
* **Enforcement:** ADVISORY
* **Mutable:** static
* **Description:** PLACEHOLDER: sentiment model identifier for future extension.

### NEWS_DEBUG

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `NEWS_DEBUG`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Enable verbose news debug logging.

### NEWS_ENABLED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `NEWS_ENABLED`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Enable RSS news ingestion.

### NEWS_LOOKBACK_HOURS

* **Type:** <class 'float'>
* **Default:** `6.0`
* **Env overrides:** `NEWS_LOOKBACK_HOURS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Lookback horizon in hours for news matching.

### NEWS_MAX_AGE_SECONDS

* **Type:** <class 'int'>
* **Default:** `3600`
* **Env overrides:** `NEWS_MAX_AGE_SECONDS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Max age (seconds) for news freshness gates.

### NEWS_MAX_ENTRIES_PER_SYMBOL

* **Type:** <class 'int'>
* **Default:** `5`
* **Env overrides:** `NEWS_MAX_ENTRIES_PER_SYMBOL`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Max news entries retained per symbol.

### NEWS_MAX_ITEMS_PER_FEED

* **Type:** <class 'int'>
* **Default:** `75`
* **Env overrides:** `NEWS_MAX_ITEMS_PER_FEED`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Max RSS entries processed per feed.

### NEWS_MAX_TOP_HEADLINES

* **Type:** <class 'int'>
* **Default:** `5`
* **Env overrides:** `NEWS_MAX_TOP_HEADLINES`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Max top headlines included in news context.

### NEWS_MIN_REGIONS

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `NEWS_MIN_REGIONS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum region count for news catalyst eligibility.

### NEWS_MIN_VELOCITY_10M

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `NEWS_MIN_VELOCITY_10M`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum 10-minute news velocity to qualify.

### NEWS_REFRESH_SECONDS

* **Type:** <class 'int'>
* **Default:** `90`
* **Env overrides:** `NEWS_REFRESH_SECONDS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum seconds between RSS refreshes.

### NEWS_REQUEST_TIMEOUT_S

* **Type:** <class 'int'>
* **Default:** `5`
* **Env overrides:** `NEWS_REQUEST_TIMEOUT_S`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** HTTP timeout (seconds) for news RSS requests.

### ROSS_REQUIRE_NEWS

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `ROSS_REQUIRE_NEWS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Require news headlines to pass Ross 5 pillars filter.

### VERIFIED_RSS_PATH

* **Type:** <class 'str'>
* **Default:** `verified_rss.txt`
* **Env overrides:** `VERIFIED_RSS_PATH`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Path to verified RSS sources list.

## ReplayEngine

### EVENT_REPLAY_MODE

* **Type:** <class 'str'>
* **Default:** `CYCLE`
* **Env overrides:** `EVENT_REPLAY_MODE`
* **Enforcement:** SOFT
* **Mutable:** static
* **Choices:** ['OFF', 'CYCLE', 'RUN']
* **Description:** Requested event replay mode before live safety overrides.

### EVENT_REPLAY_MODE_EFFECTIVE

* **Type:** <class 'str'>
* **Default:** `None`
* **Env overrides:** `(none)`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['OFF', 'CYCLE', 'RUN']
* **Description:** Derived event replay mode (forced OFF in live modes).

## RiskEngine

### RISK_CONFIDENCE_LOW_THRESHOLD

* **Type:** <class 'float'>
* **Default:** `0.75`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Confidence threshold for LOW risk classification.

### RISK_CONFIDENCE_MEDIUM_THRESHOLD

* **Type:** <class 'float'>
* **Default:** `0.5`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Confidence threshold for MEDIUM risk classification.

### RISK_MAX_POSITION_SIZE

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `(none)`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Max position size allowed by RiskEngine.

### RISK_STRATEGY_LIMITS

* **Type:** <class 'dict'>
* **Default:** `{"SCALPER": {"max_trades": 2}, "MOMENTUM": {"max_trades": 1}}`
* **Env overrides:** `(none)`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Per-trader strategy limits enforced by RiskEngine.

## RossMomentum

### ROSS_MAX_FLOAT

* **Type:** <class 'int'>
* **Default:** `20000000`
* **Env overrides:** `ROSS_MAX_FLOAT`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Max float shares for Ross 5 pillars filter.

### ROSS_MAX_PRICE

* **Type:** <class 'float'>
* **Default:** `20.0`
* **Env overrides:** `ROSS_MAX_PRICE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Maximum price for Ross 5 pillars filter.

### ROSS_MIN_PCT_CHANGE

* **Type:** <class 'float'>
* **Default:** `10.0`
* **Env overrides:** `ROSS_MIN_PCT_CHANGE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum percent change for Ross 5 pillars filter.

### ROSS_MIN_PREMARKET_VOLUME

* **Type:** <class 'int'>
* **Default:** `100000`
* **Env overrides:** `ROSS_MIN_PREMARKET_VOLUME`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum volume during premarket/overnight for Ross filter.

### ROSS_MIN_PRICE

* **Type:** <class 'float'>
* **Default:** `1.0`
* **Env overrides:** `ROSS_MIN_PRICE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum price for Ross 5 pillars filter.

### ROSS_MIN_RVOL

* **Type:** <class 'float'>
* **Default:** `5.0`
* **Env overrides:** `ROSS_MIN_RVOL`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum relative volume for Ross 5 pillars filter.

### ROSS_MIN_VOLUME

* **Type:** <class 'int'>
* **Default:** `1000000`
* **Env overrides:** `ROSS_MIN_VOLUME`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum volume during regular session for Ross filter.

## RossMomentumRiskOverlay

### ROSS_RISK_CONFIDENCE_FLOOR

* **Type:** <class 'float'>
* **Default:** `0.6`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum confidence for Ross momentum overlay.

### ROSS_RISK_COOLDOWN_TICKS

* **Type:** <class 'int'>
* **Default:** `5`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Cooldown ticks after Ross momentum attempt.

### ROSS_RISK_FLOAT_CEILING

* **Type:** <class 'float'>
* **Default:** `100.0`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Max float (millions) for Ross momentum overlay.

### ROSS_RISK_MAX_ATTEMPTS_PER_SYMBOL

* **Type:** <class 'int'>
* **Default:** `2`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Max Ross momentum attempts per symbol.

### ROSS_RISK_MAX_GAP

* **Type:** <class 'float'>
* **Default:** `20.0`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Maximum gap percentage for Ross momentum risk overlay.

### ROSS_RISK_MIN_GAP

* **Type:** <class 'float'>
* **Default:** `4.0`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum gap percentage for Ross momentum risk overlay.

### ROSS_RISK_RVOL_FLOOR

* **Type:** <class 'float'>
* **Default:** `2.0`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Min relative volume for Ross momentum overlay.

## Runtime

### APP_VERSION

* **Type:** <class 'str'>
* **Default:** `UNKNOWN`
* **Env overrides:** `APP_VERSION`
* **Enforcement:** ADVISORY
* **Mutable:** static
* **Description:** Application version identifier.

### GIT_SHA

* **Type:** <class 'str'>
* **Default:** `None`
* **Env overrides:** `GIT_SHA`
* **Enforcement:** ADVISORY
* **Mutable:** static
* **Description:** Git commit SHA for the running build.

## Scanner

### IBKR_AUTO_LOCKDOWN_ENABLED

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `IBKR_AUTO_LOCKDOWN_ENABLED`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Enable automatic lockdown when data quality fails.

### IBKR_CLIENT_ID

* **Type:** <class 'int'>
* **Default:** `7`
* **Env overrides:** `IBKR_CLIENT_ID`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** IBKR client ID for market data connections.

### IBKR_FALLBACK_ENABLED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `IBKR_FALLBACK_ENABLED`
* **Enforcement:** SOFT
* **Mutable:** per-cycle
* **Description:** Allow fallback scanner outputs when IBKR data is unavailable.

### IBKR_FALLBACK_SOURCE

* **Type:** <class 'str'>
* **Default:** `STATIC`
* **Env overrides:** `IBKR_FALLBACK_SOURCE`
* **Enforcement:** SOFT
* **Mutable:** per-cycle
* **Description:** Label for fallback data source when IBKR unavailable.

### IBKR_MARKET_DATA_TYPE

* **Type:** <class 'str'>
* **Default:** `LIVE`
* **Env overrides:** `IBKR_MARKET_DATA_TYPE`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['LIVE', 'DELAYED', 'DELAYED_FROZEN', 'FROZEN']
* **Description:** IBKR market data type (LIVE/DELAYED/etc).

### IBKR_MAX_SYMBOLS_PER_CYCLE

* **Type:** <class 'int'>
* **Default:** `50`
* **Env overrides:** `IBKR_MAX_SYMBOLS_PER_CYCLE`
* **Enforcement:** HARD
* **Mutable:** per-cycle
* **Description:** Upper bound on symbols that may be snapshotted per cycle.

### IBKR_SNAPSHOT_MAX_AGE_SECONDS

* **Type:** <class 'int'>
* **Default:** `15`
* **Env overrides:** `IBKR_SNAPSHOT_MAX_AGE_SECONDS`
* **Enforcement:** SOFT
* **Mutable:** per-cycle
* **Description:** Maximum age of IBKR snapshot data before treated as stale.

### IBKR_SNAPSHOT_TIMEOUT_SECONDS

* **Type:** <class 'int'>
* **Default:** `5`
* **Env overrides:** `IBKR_SNAPSHOT_TIMEOUT_SECONDS`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Timeout for IBKR snapshot requests in seconds.

### RUN_MODE

* **Type:** <class 'str'>
* **Default:** `SIM`
* **Env overrides:** `RUN_MODE`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['SIM', 'PAPER', 'LIVE', 'LIVE_READ_ONLY', 'LIVE_MICRO']
* **Description:** Baseline runtime mode before safety-derived overrides.

### RUN_MODE_EFFECTIVE

* **Type:** <class 'str'>
* **Default:** `None`
* **Env overrides:** `(none)`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['SIM', 'PAPER', 'LIVE', 'LIVE_READ_ONLY', 'LIVE_MICRO']
* **Description:** Derived run mode after safety rules (LIVE_READ_ONLY override).

### SCANNER_MODE

* **Type:** <class 'str'>
* **Default:** `TEACHING`
* **Env overrides:** `SCANNER_MODE`
* **Enforcement:** SOFT
* **Mutable:** static
* **Choices:** ['TEACHING', 'LIVE_READONLY']
* **Description:** Scanner selection mode (TEACHING/LIVE_READONLY).

### SCANNER_SESSION_WINDOWS_UTC

* **Type:** <class 'dict'>
* **Default:** `{"PRE_START": 12.0, "RTH_START": 14.0, "AFT_START": 21.5, "AFT_END": 23.0}`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** UTC hour windows for scanner session labels.

### SCANNER_SYMBOLS

* **Type:** <class 'list'>
* **Default:** `[]`
* **Env overrides:** `SCANNER_SYMBOLS, IBKR_SCAN_SYMBOLS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Explicit scanner symbol list (comma-separated).

## ScannerFilters

### NEWS_MAX_AGE_SECONDS

* **Type:** <class 'int'>
* **Default:** `3600`
* **Env overrides:** `NEWS_MAX_AGE_SECONDS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Max age (seconds) for news freshness gates.

### NEWS_MIN_REGIONS

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `NEWS_MIN_REGIONS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum region count for news catalyst eligibility.

### NEWS_MIN_VELOCITY_10M

* **Type:** <class 'int'>
* **Default:** `1`
* **Env overrides:** `NEWS_MIN_VELOCITY_10M`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum 10-minute news velocity to qualify.

### ROSS_MAX_FLOAT

* **Type:** <class 'int'>
* **Default:** `20000000`
* **Env overrides:** `ROSS_MAX_FLOAT`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Max float shares for Ross 5 pillars filter.

### ROSS_MAX_PRICE

* **Type:** <class 'float'>
* **Default:** `20.0`
* **Env overrides:** `ROSS_MAX_PRICE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Maximum price for Ross 5 pillars filter.

### ROSS_MIN_PCT_CHANGE

* **Type:** <class 'float'>
* **Default:** `10.0`
* **Env overrides:** `ROSS_MIN_PCT_CHANGE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum percent change for Ross 5 pillars filter.

### ROSS_MIN_PREMARKET_VOLUME

* **Type:** <class 'int'>
* **Default:** `100000`
* **Env overrides:** `ROSS_MIN_PREMARKET_VOLUME`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum volume during premarket/overnight for Ross filter.

### ROSS_MIN_PRICE

* **Type:** <class 'float'>
* **Default:** `1.0`
* **Env overrides:** `ROSS_MIN_PRICE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum price for Ross 5 pillars filter.

### ROSS_MIN_RVOL

* **Type:** <class 'float'>
* **Default:** `5.0`
* **Env overrides:** `ROSS_MIN_RVOL`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum relative volume for Ross 5 pillars filter.

### ROSS_MIN_VOLUME

* **Type:** <class 'int'>
* **Default:** `1000000`
* **Env overrides:** `ROSS_MIN_VOLUME`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Minimum volume during regular session for Ross filter.

### ROSS_REQUIRE_NEWS

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `ROSS_REQUIRE_NEWS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Require news headlines to pass Ross 5 pillars filter.

## ScannerMaster

### DISABLE_OSC8

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `DISABLE_OSC8`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Disable OSC-8 hyperlink formatting in scanner output.

### SHOW_URLS

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `SHOW_URLS`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Enable URL display in scanner output.

## ScannerRunner

### SCANNER_DATA_SOURCE

* **Type:** <class 'str'>
* **Default:** `AUTO`
* **Env overrides:** `SCANNER_DATA_SOURCE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Choices:** ['AUTO', 'IBKR', 'MOCK']
* **Description:** Scanner data provider selection (AUTO/IBKR/MOCK).

### SCANNER_FLOAT_CACHE_FILE

* **Type:** <class 'str'>
* **Default:** `src/scanner/float_cache.json`
* **Env overrides:** `SCANNER_FLOAT_CACHE_FILE`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Path to float cache JSON for scanner provider.

### SCANNER_GIT_SHA

* **Type:** <class 'str'>
* **Default:** ``
* **Env overrides:** `SCANNER_GIT_SHA, GIT_SHA`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Git SHA for scanner build metadata.

### SCANNER_MOCK_SEED

* **Type:** <class 'int'>
* **Default:** `42`
* **Env overrides:** `SCANNER_MOCK_SEED`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Seed for deterministic mock scanner provider.

### SCANNER_MOCK_SYMBOLS_FILE

* **Type:** <class 'str'>
* **Default:** `src/scanner/mock_universe.txt`
* **Env overrides:** `SCANNER_MOCK_SYMBOLS_FILE`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Path to mock scanner universe symbols.

### SCANNER_SESSION_WINDOWS_UTC

* **Type:** <class 'dict'>
* **Default:** `{"PRE_START": 12.0, "RTH_START": 14.0, "AFT_START": 21.5, "AFT_END": 23.0}`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** UTC hour windows for scanner session labels.

### SCANNER_TOP_GAINERS_COUNT

* **Type:** <class 'int'>
* **Default:** `50`
* **Env overrides:** `TOP_GAINERS_COUNT`
* **Enforcement:** HARD
* **Mutable:** per-cycle
* **Description:** Max symbols requested from scanner provider.

### SCANNER_VERSION

* **Type:** <class 'str'>
* **Default:** `v2026-01-04-11`
* **Env overrides:** `(none)`
* **Enforcement:** ADVISORY
* **Mutable:** static
* **Description:** Scanner contract/version identifier.

### SCANNER_WATCHLIST_LIMIT

* **Type:** <class 'int'>
* **Default:** `15`
* **Env overrides:** `(none)`
* **Enforcement:** SOFT
* **Mutable:** per-cycle
* **Description:** Final watchlist size cap after filtering.

## StorageEngine

### APP_VERSION

* **Type:** <class 'str'>
* **Default:** `UNKNOWN`
* **Env overrides:** `APP_VERSION`
* **Enforcement:** ADVISORY
* **Mutable:** static
* **Description:** Application version identifier.

### AUDIT_HASH_CHAIN_ENABLED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `AUDIT_HASH_CHAIN_ENABLED`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Enable audit hash chain for stored events.

### AUDIT_VERIFY_ON_START

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `AUDIT_VERIFY_ON_START`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Verify audit chain at startup.

### EVENT_REPLAY_MODE

* **Type:** <class 'str'>
* **Default:** `CYCLE`
* **Env overrides:** `EVENT_REPLAY_MODE`
* **Enforcement:** SOFT
* **Mutable:** static
* **Choices:** ['OFF', 'CYCLE', 'RUN']
* **Description:** Requested event replay mode before live safety overrides.

### FUTURE_STORAGE_RETENTION_DAYS

* **Type:** <class 'int'>
* **Default:** `0`
* **Env overrides:** `FUTURE_STORAGE_RETENTION_DAYS`
* **Enforcement:** ADVISORY
* **Mutable:** static
* **Description:** PLACEHOLDER: retention days for stored events.

### GIT_SHA

* **Type:** <class 'str'>
* **Default:** `None`
* **Env overrides:** `GIT_SHA`
* **Enforcement:** ADVISORY
* **Mutable:** static
* **Description:** Git commit SHA for the running build.

### IBKR_HOST

* **Type:** <class 'str'>
* **Default:** `127.0.0.1`
* **Env overrides:** `IBKR_HOST`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** IBKR gateway host.

### IBKR_MARKET_DATA_TYPE

* **Type:** <class 'str'>
* **Default:** `LIVE`
* **Env overrides:** `IBKR_MARKET_DATA_TYPE`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['LIVE', 'DELAYED', 'DELAYED_FROZEN', 'FROZEN']
* **Description:** IBKR market data type (LIVE/DELAYED/etc).

### IBKR_PORT

* **Type:** <class 'int'>
* **Default:** `7497`
* **Env overrides:** `IBKR_PORT`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** IBKR gateway port.

### PERSISTENCE_BACKEND

* **Type:** <class 'str'>
* **Default:** `sqlite`
* **Env overrides:** `PERSISTENCE_BACKEND`
* **Enforcement:** HARD
* **Mutable:** static
* **Description:** Persistence backend selection.

### PERSISTENCE_ENABLED

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `PERSISTENCE_ENABLED`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Enable persistence subsystem.

### PERSISTENCE_JSONL_MIRROR_ENABLED

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `PERSISTENCE_JSONL_MIRROR_ENABLED`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Enable JSONL mirroring alongside SQLite.

### PERSISTENCE_SQLITE_PATH

* **Type:** <class 'str'>
* **Default:** `data/ibkr_system.db`
* **Env overrides:** `PERSISTENCE_SQLITE_PATH`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** SQLite file path for persistence.

### PERSIST_FLUSH_EACH_CYCLE

* **Type:** <class 'bool'>
* **Default:** `True`
* **Env overrides:** `PERSIST_FLUSH_EACH_CYCLE`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Flush persistence after each cycle.

### RUN_MODE

* **Type:** <class 'str'>
* **Default:** `SIM`
* **Env overrides:** `RUN_MODE`
* **Enforcement:** HARD
* **Mutable:** static
* **Choices:** ['SIM', 'PAPER', 'LIVE', 'LIVE_READ_ONLY', 'LIVE_MICRO']
* **Description:** Baseline runtime mode before safety-derived overrides.

## Strategies

### ENABLED_STRATEGIES

* **Type:** <class 'dict'>
* **Default:** `{"GapAndGoStrategy": true, "MomentumContinuationStrategy": true}`
* **Env overrides:** `(none)`
* **Enforcement:** ADVISORY
* **Mutable:** dynamic
* **Description:** Strategy allowlist map (name -> enabled).

### MAX_HOLD_TICKS

* **Type:** <class 'int'>
* **Default:** `10`
* **Env overrides:** `MAX_HOLD_TICKS`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Maximum ticks a trade may remain open.

### MIN_HOLD_TICKS

* **Type:** <class 'int'>
* **Default:** `2`
* **Env overrides:** `MIN_HOLD_TICKS`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Minimum ticks to hold a trade before exit.

### ROSS_MOMENTUM_STRATEGY_ENABLED

* **Type:** <class 'bool'>
* **Default:** `False`
* **Env overrides:** `ROSS_MOMENTUM_STRATEGY_ENABLED`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Enable Ross Momentum strategy execution.

## SystemConfig

### ACTIVE_SESSIONS

* **Type:** <class 'list'>
* **Default:** `["PRE", "REGULAR", "AFTER"]`
* **Env overrides:** `ACTIVE_SESSIONS`
* **Enforcement:** SOFT
* **Mutable:** static
* **Description:** Market sessions considered active for safety checks.

### MARKET_EARLY_CLOSE_TIME

* **Type:** <class 'datetime.time'>
* **Default:** `13:00`
* **Env overrides:** `MARKET_EARLY_CLOSE_TIME`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Early close time for half-day sessions (HH:MM).

### MARKET_HALF_DAYS

* **Type:** <class 'set'>
* **Default:** `set()`
* **Env overrides:** `MARKET_HALF_DAYS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Comma-separated list of YYYY-MM-DD half-day sessions.

### MARKET_HOLIDAYS

* **Type:** <class 'set'>
* **Default:** `set()`
* **Env overrides:** `MARKET_HOLIDAYS`
* **Enforcement:** SOFT
* **Mutable:** dynamic
* **Description:** Comma-separated list of YYYY-MM-DD market holidays.

### MARKET_SESSION_WINDOWS_LOCAL

* **Type:** <class 'dict'>
* **Default:** `{'PRE_START': datetime.time(4, 0), 'REGULAR_START': datetime.time(9, 30), 'REGULAR_END': datetime.time(16, 0), 'AFTER_END': datetime.time(20, 0)}`
* **Env overrides:** `(none)`
* **Enforcement:** ADVISORY
* **Mutable:** static
* **Description:** Local time windows for PRE/REGULAR/AFTER sessions.

## TradeExitEngine

### MAX_HOLD_TICKS

* **Type:** <class 'int'>
* **Default:** `10`
* **Env overrides:** `MAX_HOLD_TICKS`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Maximum ticks a trade may remain open.

### MIN_HOLD_TICKS

* **Type:** <class 'int'>
* **Default:** `2`
* **Env overrides:** `MIN_HOLD_TICKS`
* **Enforcement:** HARD
* **Mutable:** dynamic
* **Description:** Minimum ticks to hold a trade before exit.
