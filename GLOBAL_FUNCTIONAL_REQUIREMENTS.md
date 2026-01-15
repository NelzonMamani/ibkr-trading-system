# GLOBAL_FUNCTIONAL_REQUIREMENTS
Last updated: 2026-01-15

## 1. Purpose
This document defines the **global functional requirements** for the ibkr-trading-system (“Trading OS”).
It exists to:
- Prevent scope drift and cross-module leakage
- Ensure deterministic behaviour
- Provide operator-grade console outputs
- Make acceptance provable via **run commands + logs + tests**

This file is subordinate only to:
- `SYSTEM_CONSTITUTION.md` (law; immutable)
- `README.md` (public charter)
- `SYSTEM_STATE.md` (authoritative snapshot)

## 2. System Definition
The Trading OS is a modular system that can operate in standalone (module-by-module) and integrated modes.

### 2.1 End-to-End Pipeline (Single Cycle)
1) **Scanner** discovers candidates and outputs: **Watchlist K** and **Focus M**  
2) **Data Hydration** fetches bars/quotes/indicators for Focus symbols  
3) **Patterns** detect setups and output PatternResults (no trades)  
4) **Strategy** converts PatternResults to TradeIntents (no orders)  
5) **Risk** applies final gating and sizing constraints  
6) **Execution** interacts with IBKR only when permitted  
7) **Storage** persists full chain for audit + replay  
8) **Health** summarizes system condition and enforcement state

## 3. Operating Modes (Mandatory)
The system must support three explicit modes; **mode must be printed at startup and every cycle**:
- **SIM**: simulation mode, no broker orders
- **READONLY**: live observation, no broker orders; logs “would place” instead
- **LIVE_1SHARE**: live execution enabled but constrained to 1-share default sizing (risk can block or further constrain)

**Mode Law:** under no circumstances may SIM or READONLY submit or modify broker orders.

## 4. Deterministic Orchestrator (Mandatory)
### 4.1 Deterministic Cycle Order
Scanner → Data → Patterns → Strategy → Risk → Execution → Storage → Health

### 4.2 Non-overlap Guarantee
Cycles must not overlap. If a cycle exceeds the configured interval, the next cycle must be delayed (not parallelized).

### 4.3 Deterministic Inputs
Given identical inputs within a cycle:
- outputs must be identical (same K/M lists, same decisions) except for timestamp fields.

## 5. Scanner Contract (Frozen)
**Top N gainers → Hard gates → Watchlist K → Focus M**

Defaults:
- Watchlist K: default 15 (configurable up to 30)
- Focus M: default 3–5 (configurable up to 10)

### 5.1 Empty Watchlists are Valid
If no symbols survive, the scanner must print:
- `EMPTY WATCHLIST (valid)`
- a compact drop-reason summary (histogram-style)

## 6. Strategy Class: Ross Momentum (Epoch 5)
Epoch 5 completes the intraday momentum strategy class (Ross-first), but keeps architecture strategy-agnostic.

Global rules:
- Strategy produces **TradeIntents only** (no broker actions)
- Risk is final authority
- Execution is broker-only and must obey mode law
- Storage is mandatory

## 7. Risk as Final Authority (Mandatory)
Risk must:
- be able to block any intent
- explain decisions with rule triggers and thresholds
- enforce circuit breakers (daily loss, max trades, health CRITICAL, data quality)

## 8. Storage is Non-Optional (Mandatory)
Persist full chain of artifacts and events:
ScannerArtifact → PatternResults → TradeIntents → RiskDecisions → ExecutionEvents → Outcome

If storage fails:
- system must degrade (DEGRADED) and/or halt trading actions depending on severity
- in LIVE_1SHARE, inability to persist must be treated as CRITICAL

## 9. Operator-Grade Console Output (Mandatory)
Every cycle must print (minimum):
- Mode, Session state, Cycle ID
- Scanner: TopN count, Survivors count, DropReasons summary, WatchlistK list, FocusM list
- Patterns: best setup per Focus symbol with confidence
- Strategy: intents emitted (count and summary)
- Risk: ALLOW/BLOCK with rationale
- Execution: READONLY logs “would place”; LIVE_1SHARE logs “submitted/fill/etc.”
- Storage: confirmation of persisted record counts
- Health: OK/DEGRADED/CRITICAL + reasons

## 10. Minimum Test Coverage (Epoch 5 Completion)
- Import/package smoke test (no ModuleNotFoundError)
- Scanner contract test (K/M printed + empty-valid behaviour)
- Orchestrator READONLY one-cycle test (end-to-end without broker action)
- Risk circuit breaker tests (CRITICAL blocks)
- Execution mode law test (no broker calls in READONLY/SIM)

## References (Primary / High-signal)
The following public Warrior Trading resources informed these requirements:
- Flat Top Breakout Pattern (how Ross trades it): https://www.warriortrading.com/flat-top-breakout-pattern/
- Bull Flag pattern guide: https://www.warriortrading.com/bull-flag-trading/
- Momentum Day Trading Strategy overview: https://www.warriortrading.com/momentum-day-trading-strategy/
- Stock selection / watchlist criteria (gap/float/RVOL/catalyst concepts): https://www.warriortrading.com/day-trading-watch-list-top-stocks-to-watch/
- “20-20” heuristic (under $20, under 20M float): https://www.warriortrading.com/simplest-day-trading-strategy/
- Technical Analysis PDF (includes Micro Pullback discussion): https://media.warriortrading.com/2022/06/03110459/Technical-Analysis-v3.pdf
- Intraday Chart Patterns PDF (flat top / whole-dollar breaks etc.): https://media.warriortrading.com/2014/09/WarriorTrading-DayTradingCourse-Class5.pdf


END.
