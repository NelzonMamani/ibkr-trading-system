# Phase 24 — Configuration Authority

This document explains why configuration is centralized and enforced.

## Why this exists

Configuration is now resolved through a single registry and resolver to eliminate
implicit defaults, hidden environment dependencies, and runtime ambiguity.

## What changed

* **Registry size:** 116 variables
* **HARD enforced:** 27
* **SOFT:** 80
* **ADVISORY:** 9

## How ambiguity was eliminated

* Public runtime policy uses `get_config` and the resolver. Optional standalone
  provider credentials remain private environment inputs to their existing adapters;
  they must not enter registry dumps or resolution traces. See the operator guide below.
* Environment variables are parsed once and validated for type/constraints.
* Derived values (e.g. effective run mode) are explicitly recorded.
* A structured CONFIG_RESOLVED event is emitted at startup.

## Future extension pattern

1. For nonsecret runtime policy, add an entry to `CONFIG_REGISTRY` with type, default, env overrides, and metadata. Never add credentials/contact values to the public registry.
2. Add enforcement rules or validation in `config_resolver` if needed.
3. Regenerate documentation by running the config docs generator.

## Scanner authority (Ross Momentum)

* Stock selection thresholds now live in `RossMomentumPolicy.stock_selection`.
* The orchestrator loads the strategy policy and delegates that stock selection policy to the scanner.
* The scanner executes the provided policy and reports watchlist/focus outputs back to the orchestrator.

## Operator provider settings (canonical guide)

This is the canonical provider environment-key table. The generated
[Configuration Reference](CONFIGURATION_REFERENCE.md) documents the remaining
public registry settings; dated checkpoint inventories are historical receipts.
There is no second settings file, `.env` loader or credential store. Ignoring
`.env*` in Git does not load it or secure it. Do not create copies of credentials
in `.env`, source, tests, manifests or diagnostic projections.

| Environment key(s) / selection | Purpose and consumer / launcher | Required or optional; absent/disabled behavior |
| --- | --- | --- |
| `RUN_MODE`, `SCANNER_DATA_SOURCE` | Runtime resolver / scanner factory. Python entry points inherit the launching process environment. `AUTO` selects MOCK in SIM/PAPER, IBKR in READ_ONLY/LIVE; explicit IBKR selects a connection. | Select modes deliberately; the registry default is LIVE, not SIM. MOCK supports offline research, not natural acceptance or trading certification. |
| `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`, `IBKR_MARKET_DATA_TYPE` | Runtime accessors, existing connection/market-data owners. TWS/Gateway owns broker login and API settings; Python does not store the broker password. | Required connection/data for the chosen real broker path. Missing/failed connection is not empty positions, orders or valid quotes. Delayed data is not automatically eligible fresh evidence. |
| `IBKR_CLIENT_ID_ORDER_SUBMIT`, `IBKR_READONLY_ENABLED`, `IBKR_API_WRITE_ALLOWED`, `EXECUTION_ENABLED` | Existing runtime/execution authority. Effective mode/order permissions are derived, not granted by setting a flag. | READ_ONLY remains nonmutating. Broker trading requires the real connection AND all ownership, risk and execution gates. Do not change these controls to overcome missing evidence. |
| `NEWS_ENABLED`, `NEWS_MAINTENANCE_ENABLED` | Scanner and runtime-owned canonical news maintenance. Restart to change maintenance ownership; news-disable stops the pinned owner without a competing writer. | News may be disabled for offline work; this cannot bypass Ross's mandatory catalyst. Maintenance-disable alone is not a universal acquisition-off switch. |
| `ROSS_ISSUER_QUERY_ENABLED` | Existing canonical issuer-query route policy. | Optional existing route opt-in; no new sources or fallback on missing credentials. Preserve accepted harness policy. |
| `NEWS_CACHE_FILE`, `NEWS_LOOKBACK_HOURS`, `NEWS_MAX_AGE_HOURS`, `NEWS_REQUEST_TIMEOUT_S`, `NEWS_TOTAL_BUDGET_S`, `NEWS_EXTENDED_TIER_RESERVE_FRACTION` | Existing news cache, freshness and bounded scheduler owners. Source membership remains in existing source-group/query owners. | Paths and budgets are not secrets. No change here authorizes stale data, expanded fanout, renewed deadlines or another canonical writer. |
| `SCANNER_FLOAT_CACHE_FILE`, `PERSISTENCE_SQLITE_PATH` | Existing float/cache and persistence owners. | Data storage, not credentials. Cache-first reference discovery preserves its existing Yahoo/Finviz/last-known-good policy. Missing float stays UNKNOWN; stored provenance does not grant trading eligibility. |
| `MASSIVE_API_KEY` (preferred), `POLYGON_API_KEY` (legacy fallback) | `massive_news_adapter.py` reads private process environment when instantiated; `scripts/verify_news_discovery.py --provider massive` selects it. Default provider is RSS. Existing [W04 instructions](architecture/W04_HISTORICAL_NEWS.md) use concealed local entry/clearing. | Optional standalone research only. Neither SIM/MOCK nor RSS requires these credentials. Missing key => `missing_credential`; unavailable HTTP library => `requests_unavailable`; no automatic substitute provider. Do not infer account/subscription from another service's contact. |
| `SEC_REQUEST_CONTACT` | Launch-only private environment carrier for the separately reviewed one-off SEC capture. NO production SEC loader, registered key or source association consumes it. The future capture caller must explicitly read it. | SEC configuration/capture PARKED. Not saved by this work; no contact in repository/fixtures/shareable reports. It grants neither publisher verification nor production enrollment. |

Yahoo/yfinance and Finviz float paths use no API key here. Selecting Yahoo loads
`yfinance`; selecting Finviz loads `requests` and `bs4`. A cache hit or mock startup
does not load those packages through the float owner. `YFINANCE_UNAVAILABLE`,
`REQUESTS_UNAVAILABLE` and `BEAUTIFULSOUP_UNAVAILABLE` identify a missing selected
package, not a provider response. An unrelated import failure in an installed
package propagates: broken installation is not silently relabelled missing data.
Existing installed-provider request timeouts, parsing and cache/fallback behavior
are unchanged. Requests remains a declared repository dependency; the real IBKR
scanner module still imports it when the IBKR provider is selected. BeautifulSoup
is not directly listed in requirements.txt; installed yfinance normally supplies
it transitively. No packages were installed or dependency declarations changed.

### Windows location, precedence and scope

For ordinary Python launches, set nonsecret keys in the launching PowerShell
session (`$env:NAME = 'value'`) or PyCharm **Run > Edit Configurations > Environment
variables**. A Run configuration does not modify a terminal that is already open.
PyCharm may serialize environment values in local IDE files; they are not a vault.
For private values prefer the existing concealed prompt/process-only pattern,
then clear the variable. Never put a key/contact literal in command history.
No credentials are needed merely to run tests or SIM/MOCK offline controls.

Process environment is inherited by child processes; it expires when that process
exits. Windows User/Machine persistent environment is separate: edit through
**System Properties > Advanced > Environment Variables** for intended nonsecret
defaults, then start a NEW terminal/IDE to inherit it. This project does not directly
read the Windows User/Machine registry or choose between three secret copies.
`$env:` assignment overrides the inherited process value; deleting it does not
rewrite persistent User/Machine values. Do not duplicate a credential across scopes.

General resolver precedence is in-process overrides > inherited process environment
> registry defaults, followed by derived safety rules. Runtime mode authority can
restrict execution regardless of input flags. Massive reads its own named private
environment inputs, outside the logging registry. These are existing owners, not
interchangeable sources. No private input should be put into a general config dump.

The existing certification launcher
`scripts/certification/run_natural_readonly_observation.ps1` invokes
`natural_readonly_operator.py`, which strips registry environment overrides and
builds a pinned safe environment. It sets its own broker/news values and isolated
cache paths. Generic terminal values do NOT override that contract. The launcher
is NOT a SEC/Massive credential management command. Do not launch it during this
configuration task, or run a preparation helper merely to test settings.

Presence-only checks, with no secret/contact values printed:

```powershell
foreach ($name in @('MASSIVE_API_KEY','POLYGON_API_KEY','SEC_REQUEST_CONTACT')) {
    foreach ($scope in @('Process','User','Machine')) {
        $present = -not [string]::IsNullOrWhiteSpace(
            [Environment]::GetEnvironmentVariable($name, $scope))
        [pscustomobject]@{ Key = $name; Scope = $scope; Configured = $present }
    }
}
```

Only **Process** describes what a child launched from this shell will consume.
Configured means nonblank, not valid, entitled, live-verified or authorized for a
new operation. No account-management/login URL is documented in the existing
provider material; do not invent one. Existing Massive links are API documentation.
Do not visit account/provider services merely to validate configuration.

### Distinguish four failure layers

- **Missing Python package:** selected optional source reports its named unavailable
  reason. Unrelated module initialization/dependency errors propagate; install
  diagnosis is separate from credentials and was not performed by making requests.
- **Missing credential:** explicit Massive selection cannot acquire; no paid key
  is required for unrelated offline stages. No fallback account is guessed.
- **Unavailable service:** HTTP/access/timeout/deadline failures retain incomplete
  coverage and original reasons. Alternatives run only under established policy.
- **Missing required trading evidence:** unknown/stale/unattributed float, quote,
  catalyst, position/order truth or timeframe inputs remain blocked even if all
  packages and credentials are present. Five unmatched positions still veto new
  entry admission after formation and before canonical artifact/risk admission.

Historical receipts and natural positive catalyst-to-intent proof remain separate.
SIM fixtures, configuration checks and optional-dependency tests are not natural
acceptance, broker execution or PAPER readiness.
