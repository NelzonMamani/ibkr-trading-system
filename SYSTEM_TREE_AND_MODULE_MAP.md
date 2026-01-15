# SYSTEM_TREE_AND_MODULE_MAP
Last updated: 2026-01-15

## 1. Purpose
Defines the canonical module topology, authority boundaries, and integration contracts.
This is the anti-regression document that prevents the “imports break / responsibility leaks” failure mode.

## 2. Canonical Module Tree (Logical)
Your repo may use different folder names, but the logical roles are fixed:

1) **core_engine**
   - orchestrator, run modes, health, scheduling, lifecycle control
2) **scanner**
   - market discovery: TopN → gates → WatchlistK → FocusM
3) **data**
   - data hydration for Focus symbols (bars/quotes/indicators)
4) **patterns**
   - pattern detectors that output PatternResults (no intent, no orders)
5) **strategies**
   - strategy policy that outputs TradeIntents
6) **risk**
   - final authority: gating, sizing, circuit breakers
7) **execution**
   - broker adapter and order lifecycle tracking
8) **storage**
   - persistence and audit trails, replay inputs, reporting
9) **utils**
   - logging, config, time/session helpers, validation utilities

## 3. Authority Boundaries (Hard Rules)
### 3.1 “Never Trade” Modules
- scanner
- patterns
- strategies

These modules may only:
- compute / decide / label
- print / log / explain
- produce artifacts for downstream modules

### 3.2 Final Authority
- risk is the final authority; it may veto anything and must explain why

### 3.3 Broker Authority
- execution is the only module that touches broker APIs
- execution may only act on risk-approved TradeIntents and must obey mode law

### 3.4 Storage Authority
- storage never decides; it persists everything (including failures, blocks)

## 4. Integration Contracts (Types)
### 4.1 ScannerArtifact
Required fields:
- cycle_id, timestamp, mode, session_state
- topn_count, survivors_count
- watchlist_k: list[str]
- focus_m: list[str]
- per_symbol metrics (price, %change, gap, volume, avg_volume, rvol, spread, float if available)
- per_symbol drop_reasons (list of codes)
- drop_reason_summary (histogram)

### 4.2 DataSnapshot
For each Focus symbol:
- candles (1m minimum), vwap, ema9 (min), ema20 optional
- premarket high, OR high/low, HOD, key levels
- spread, liquidity indicators
- data quality flags

### 4.3 PatternResult
- setup_id, detected, confidence, rationale_text
- entry_zone, stop_suggestion, tags
- risk_flags + data_quality_flags

### 4.4 TradeIntent
- symbol, side, setup_id
- entry trigger definition (level + condition)
- stop plan (structure-based)
- optional target plan
- validity window + session context
- rationale

### 4.5 RiskDecision
- decision ALLOW/BLOCK/ALLOW_WITH_CONSTRAINTS
- sizing constraints
- triggered rules + thresholds
- rationale_text

### 4.6 ExecutionEvents
- submitted/acknowledged
- partial fill
- filled
- cancelled
- rejected
- error/warn messages

## 5. Cycle Data Flow
ScannerArtifact → FocusSymbols → DataSnapshot → PatternResults → TradeIntents → RiskDecisions → ExecutionEvents → StorageRecords

## 6. Required Console UX (Cycle Banner)
At minimum:
- `MODE=<...> SESSION=<PRE|REG|AFTER> CYCLE=<id>`
- `WATCHLIST_K: [..]`
- `FOCUS_M: [..]`
- `EMPTY WATCHLIST (valid)` if applicable

END.
