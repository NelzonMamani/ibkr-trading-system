# M1 Architecture Map (Authoritative)

## Scope
This document captures the authoritative architecture map for the Trading OS as implemented in the current repository.
It is documentation-only and does **not** introduce or change runtime behavior.

## Sources of Truth
- `SYSTEM_TREE_AND_MODULE_MAP.md` (logical module topology)
- `src/` directory structure (implementation reality)
- `src/directory_tree_report.txt` (captured repo tree snapshot)

## Major Subsystems (Repository Reality)
| Subsystem | Primary repo locations | Responsibility | Authority |
| --- | --- | --- | --- |
| Core orchestration | `src/core/`, `src/core_engine/`, `src/cli/`, `src/main.py` | Lifecycle control, run modes, orchestration, scheduling, health gates | Owns cycle sequencing and stage boundaries |
| Market data access | `src/market_data/`, `src/ibkr/`, `src/adapters/` | Market data connectivity, provider hubs, adapters | Supplies facts only; no policy |
| Scanner layer | `src/scanner/` | Market discovery, watchlist generation, focus set derivation | Never trades; emits scan artifacts only |
| Data hydration | `src/data/`, `src/prep/` | Focus symbol data hydration, preprocessing | Supplies enriched data snapshots only |
| Pattern detection | `src/patterns/`, `src/signals/` | Pattern detection, signal computation | Never trades; emits pattern results |
| Strategy policy | `src/strategies/`, `src/strategy/`, `src/strategy_portfolio/` | Strategy policy, intent generation, portfolio rules | Decides intent only; no execution |
| Risk engine | `src/risk/` | Risk gating, sizing, constraints, veto authority | Final authority over trade intent |
| Execution engine | `src/execution/` | Order lifecycle, execution providers, exit mechanics | Only module authorized to submit orders |
| Broker adapters | `src/broker/`, `src/brokers/` | Broker abstraction, IBKR and sim adapters | Translates execution decisions to broker API |
| Storage & audit | `src/storage/`, `src/logs/`, `src/output/` | Persistence, audit trails, replay inputs, reporting | Passive persistence; no policy decisions |
| Verification & audit tooling | `verification_scripts/`, `src/tools/`, `TRADING_OS_MASTER_CATALOGUE/` | Verification tooling, audit evidence generation | Metadata-only; never touches runtime flow |
| Metadata & configuration | `src/metadata/`, `src/config/`, `src/domain/`, `src/utils/`, `src/models/` | Canonical configuration, schema, types, utilities | Supports all subsystems; no trading authority |
| Learning & analytics | `src/learning/`, `src/performance/`, `src/regime/` | Regime/learning analytics, performance telemetry | Non-authoritative analytics only |

## Data Flow Direction (Authoritative)
1. **Market Data Providers → Scanner** (market facts feed scans)
2. **Scanner → Watchlist/Focus** (focus set output)
3. **Focus → Data Hydration** (data snapshots built)
4. **Data → Pattern Detection** (pattern results)
5. **Pattern Results → Strategy Policy** (intent generation)
6. **Strategy Policy → Risk Engine** (risk gating and sizing)
7. **Risk Engine → Execution Engine** (risk-approved orders)
8. **Execution Engine → Broker Adapters** (order submission)
9. **Broker/Execution → Storage** (audit, replay, reporting)

## Authority Boundaries (Hard Rules)
- **Scanner, Patterns, Strategies**: never submit orders; emit artifacts only.
- **Risk Engine**: final authority; may veto any intent with rationale.
- **Execution Engine**: only component allowed to submit/cancel orders.
- **Broker Adapters**: translate execution decisions; no policy logic.
- **Storage**: passive persistence only; no trading decisions.
- **Metadata/Verification**: no runtime mutations.

## Non-Goals and Forbidden Couplings
- Scanner/pattern/strategy modules must **not** call execution APIs directly. Scanner access to broker adapters is limited to market data connectivity and health checks only (no order submission).
- Risk must **not** bypass execution to place orders.
- Metadata epochs (M0–M10) must never alter runtime flow.
- No circular dependencies between core subsystems.

## Certification Verdict
Architecture map aligns with current repository structure and governance intent.
See `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/M1_ARCHITECTURE_MAP/` for verification evidence.

END
