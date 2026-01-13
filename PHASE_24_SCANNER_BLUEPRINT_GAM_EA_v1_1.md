# PHASE 24 — Scanner Blueprint (GAM‑EA Fork)

## Purpose
This document defines the **authoritative scanner blueprint** to be implemented in Phase 24.
It replaces heuristic growth of the scanner with a **statistically defensible, cache‑first, incremental design**.

The scanner remains **strategy‑agnostic**, but introduces a **formal fork** to support:
- Ross Momentum (confirmation‑based)
- GAM‑EA (early attention momentum)

## Core Scanner Responsibilities
- Produce a **tradable watchlist**
- Maintain explainability and determinism
- Enforce hard tradability gates
- Provide structured outputs to downstream strategies

## Architectural Principles
1. Decision‑first, enrichment‑last
2. Cache static data (float, history) once per session
3. Incremental per‑cycle updates
4. Early rejection with explicit drop reasons
5. News evaluation is **strategy‑specific**, not global

## Scanner Pipeline (Phase 24)

### Stage 0 — Session Bootstrap
- Cache float once per day
- Cache baseline historical volume & prior close
- Initialise symbol state & drop ledger

### Stage 1 — Market Lens
- Pull Top N US % Gainers from IBKR (N=50–100 configurable)
- Collect L1 snapshot only

### Stage 2 — Hard Tradability Filters
Mandatory gates:
- Price ∈ [2, 20]
- % Change ≥ 5%
- RVOL ≥ 2.0
- Intraday Volume ≥ 500k
- Spread ≤ configured threshold
- Float ≤ 30M (from cache)

Failing any gate → immediate drop + reason logged.

### Stage 3 — Watchlist Construction
- Rank survivors by:
  1. % Change
  2. RVOL
  3. Liquidity quality
- Select top K (default 10–15, max 30)

### Stage 4 — Strategy‑Aware News Enrichment
News processing is **deferred** and **forked**:

#### Ross Fork
- Confirm catalyst legitimacy
- Pattern‑friendly context

#### GAM‑EA Fork
- Enforce news age ≤ 6 hours
- Measure attention acceleration only
- No sentiment, no NLP, no keyword scoring

### Stage 5 — Output
- Produce watchlist with **reduced field set**
- Full links printed **only** for top 3–5 symbols
- Structured return for Strategy Engine

## Modified Field Contract (Phase 24)
Removed from hot path:
- Sentiment scores
- Region counts
- Keyword weights
- Long headline lists

Kept:
- news_present
- news_first_seen_timestamp
- catalyst_type
- dilution_flag
- short‑term news velocity (5m, 10m, 30m)

## Acceptance Criteria
- Scanner latency reduced ≥ 3× at market open
- Deterministic outputs per cycle
- Explicit drop reasons logged
- Watchlist unchanged in intent, improved in speed

This document is the **single source of truth** for Phase 24 scanner work.

---

## v1.1 Clarifications (January 2026)

### 1) Scanner responsibility boundaries (non‑negotiable)
The scanner is **strategy‑agnostic**. It is responsible for:
- Building a **tradable candidate set** (Top N → gated survivors → Watchlist K)
- Producing **fast, deterministic, explainable** outputs (FAST_VIEW + DEEP_VIEW)
- Providing **context** and **evidence hooks** for downstream consumers (strategies, learning, UI)

The scanner is **not** responsible for:
- Trade entry/exit decisions
- Position sizing
- Stop placement or trailing logic
- Online optimisation of parameters

All trade management and parameter adaptation belongs to:
- Strategy modules (deterministic decisions)
- Learning & Adaptation framework (offline diagnostics → recommendations → versioned changes)

### 2) Fork naming alignment
This blueprint originally used the label **GAM‑EA** to describe the “early-entry/attention” fork.
The corrected strategy intent is now **EEMC (Early Entry Momentum Continuation)**:
- Early positioning is permitted under strict gates
- Post‑confirmation management is Ross‑style continuation logic

Phase 24 scanner work remains valid. The fork is still a *scanner output view* (news/attention context), not strategy logic.

### 3) Learning hooks (data, not decisions)
Phase 24 must ensure the scanner emits fields sufficient to support learning attribution without embedding learning logic:
- `data_quality_flags` (FLOAT_UNKNOWN, NEWS_DELAYED, HISTORY_UNKNOWN, DATA_STALE)
- `drop_reason` for every excluded symbol
- `news_age_minutes` and velocity windows (5m/10m/30m) **only if cheap**
- `attention_tier` (deterministic bucket) rather than opaque “scores”

### 4) Print contract clarification
- **FAST_VIEW** is printed for every watchlist symbol (K) and must be cheap.
- **DEEP_VIEW** is printed only for focus symbols (top 3–5) and may include:
  - Top 3–5 unique links (unique domains preferred)
  - 1–2 line catalyst rationale
  - 1–2 line “why in focus list” explanation

### 5) Provider interfaces (future-proofing)
Phase 24 should formalise provider interfaces so we can swap data sources without rewriting the scanner:
- `FloatProvider` (cache-first)
- `HistoryProvider` (baseline cache)
- `NewsDiscoveryProvider` (Provider A = verified RSS; Provider B = optional Google later)

The scanner must tolerate provider failure and degrade gracefully via `data_quality_flags`.

### 6) Determinism and auditability
All ranking must be deterministic with stable tie-breakers:
1) primary metric(s)
2) secondary metric(s)
3) symbol ascending

All stage decisions must be auditable via:
- per-symbol drop reason
- per-cycle summary counts
- per-cycle elapsed time

---
