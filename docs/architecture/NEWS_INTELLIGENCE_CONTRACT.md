# News Intelligence Contract

## Purpose

This document defines the strategy-agnostic News Intelligence contract and the PR1069 completion path. News Intelligence now owns the canonical objective evidence/cache path for Ross READ_ONLY news retrieval. It does not own Ross trading interpretation, Ross thresholds, PAPER authority, LIVE authority, or broker-order authority.

## Ownership Boundary

News Intelligence owns objective news evidence: source retrieval facts, normalized article facts, entity matches, freshness, reliability, heat, velocity, cache state, prep reuse, and retrieval availability.

Strategies own interpretation. Ross consumes News Intelligence through scanner-side policy code in `src/scanner/scanner_runner.py`; common news code must not import `src.strategies.ross_momentum` and must not encode Ross trading decisions, catalyst keywords, dilution keywords, or thresholds.

Dependency direction:

```text
News Intelligence evidence/cache
        ^
        |
Strategy adapter / scanner policy
```

## WHAT vs WHERE

`NewsRequest` describes WHAT evidence a consumer asks for: strategy identity, event classes, freshness/lookback windows, generic-news inclusion, heat, velocity, reliability, result limits, session phase, and audit reason.

`RetrievalPolicy` describes WHERE and HOW evidence may be obtained: source groups, provider groups, cache read/write permission, refresh mode, network permission, total and tier budgets, timeout policy, fallback mode, and source/item limits.

The common contract does not put Ross price, gap, float, volume, RVOL, session, pattern, entry, stop, or target thresholds into either object.

## Source Group Authority

`src/news/source_groups.py` is the canonical strategy-neutral authority for active source-group membership and ordering. It describes the current active groups `FAST_TRADING`, `PREP_EXTENDED`, and `MACRO_LONG_HORIZON`, and it records `VERIFIED_RSS_LEGACY` as metadata for the historical `verified_rss.txt` catalogue.

`src/news/rss_registry.py` remains a compatibility export layer for existing call sites. Existing imports of `RSS_FAST_TRADING`, `RSS_PREP_EXTENDED`, `RSS_MACRO_LONG_HORIZON`, and `RSS_REGISTRY` continue to receive the same ordered URL lists.

`verified_rss.txt` and legacy `src/scanner/news_engine.py` are not wired into the active Ross scanner path. They remain historical/legacy catalogue infrastructure until a later reviewed migration explicitly changes that behavior.

## Batch-First Model

`NewsIntelligenceProvider.get_news(candidates, request, retrieval_policy)` is batch-first and returns `NewsBatchResult`. A single-symbol lookup is represented as a batch of one. Providers can fetch each source once, parse once, and match many symbols.

`src/news/batch_rss_adapter.py` adapts the existing `src/news/news_fetcher.py` batch RSS functions. It keeps source memberships and URL order from `src/news/source_groups.py`, uses bounded fast-tier-first retrieval, and only asks `PREP_EXTENDED` for strategy-supplied unresolved symbols when the budget still allows it.

## Canonical Evidence And Cache

`src/news/evidence_store.py` is the canonical evidence/cache bridge. It uses the existing `NEWS_CACHE_FILE` and stores common evidence under the `news_intelligence` namespace while preserving the legacy top-level `symbols` cache shape used by `src/data/news/news_provider.py`.

Read path:

```text
NEWS_CACHE_FILE
  -> news_intelligence.symbols[SYMBOL].evidence
  -> legacy symbols[SYMBOL].news_context
  -> canonical premarket prep artifact news_context
  -> NewsEvidence / NewsEvidenceSummary
```

Write path:

```text
NewsBatchResult.evidence_by_symbol
  -> dedupe and metric enrichment
  -> NEWS_CACHE_FILE.news_intelligence.symbols[SYMBOL].evidence
```

The store enriches evidence through existing freshness, reliability, heat, and velocity infrastructure. Cache hits, stale cache misses, prep reuse, source provenance, match types, reliability, heat, velocity, and freshest evidence ages are exposed in retrieval diagnostics.

## Prep Reuse

Prepared and overnight evidence remains authoritative when it is fresh. The active Ross scanner no longer performs a parallel scanner-side prep-news shortcut for catalyst qualification. Instead, the scanner asks News Intelligence first; the evidence store reuses canonical premarket prep entries and maps them to objective `NewsEvidence`. Ross then interprets those facts in scanner policy using the existing prep tag mapping and catalyst/dilution logic.

## Ross Runtime Migration

Before PR1069, Ross READ_ONLY news retrieval called RSS fetchers directly from `src/scanner/scanner_runner.py`, maintained an in-memory `_NEWS_CACHE`, and separately merged prep news contexts.

After PR1069, Ross READ_ONLY retrieval calls `CanonicalNewsIntelligenceService`:

```text
Ross scanner symbols
  -> NewsCandidate batch
  -> cache/prep-only News Intelligence read
  -> fast News Intelligence refresh for unresolved symbols
  -> Ross catalyst qualification in scanner policy
  -> PREP_EXTENDED News Intelligence refresh only for still-unresolved symbols
  -> Ross catalyst qualification in scanner policy
```

The scanner still owns Ross catalyst keywords, dilution keywords, freshness qualification, catalyst status, focus diagnostics, and all price/gap/float/volume/RVOL/session/pattern/risk gates. Generic news does not become a catalyst, retrieval unavailable does not become catalyst absence, and budget exhaustion remains fail-closed.

## Evidence Model

`NewsEvidence` preserves normalized objective facts:

- identity and entity-match fields;
- headline, summary, URL, event/catalyst classification, generic status, and dilution/offering status;
- published, fetched, first-seen, age, freshness, stale, and decay fields;
- source, provider, source group/tier, verified-source, reliability, credibility, and region fields;
- duplicate cluster, publication count, and independent source count;
- velocity, heat, hotness, and spike evidence;
- cache state, retrieval status, timeout, failure, and budget-exhaustion facts;
- raw and audit provenance.

Providers are not required to populate every field. Optional and unknown values are valid.

## Separate Dimensions

Reliability, freshness, heat, velocity, event classification, and retrieval availability are separate dimensions. High-reliability stale news, low-reliability high-heat news, and budget-exhausted unavailable retrieval are all representable without collapsing them into a single opaque score.

`NewsEvidenceSummary` is a latency-friendly per-symbol summary, not a trading decision. It can expose evidence counts, fresh evidence counts, qualifying event-class counts, generic evidence counts, freshest age, reliability, heat, velocity, source counts, retrieval status, provider status, cache state, budget exhaustion, and diagnostics.

It must not expose Ross decisions such as buy/pass/A-quality labels, and it must not treat retrieval unavailable or budget exhaustion as no catalyst.

## Volume vs RVOL

Absolute share volume and Relative Volume/RVOL are distinct upstream concepts. `NewsCandidate` may carry `absolute_share_volume` and `relative_volume_rvol` for prioritization or audit context, but News Intelligence does not calculate either value and is not the authority for either value.

This preserves the Ross contract: Price, Gap / percentage move, Float, Volume, and News / catalyst remain the five stock-selection pillars, while RVOL remains a supporting metric.

## Runtime Shutdown

PR1069 also fixes the post-PR1040 observe shutdown hang. A manager-owned `MarketDataClient.disconnect()` must delegate to `IbkrConnectionManager.disconnect(reason="market_data_client_disconnect")` instead of returning early. PR1040 cleanup can then tear down the shared IBKR client and avoid leaving the manager-owned thread/resource lifecycle active after `[PR1040][OBSERVE]` completes.

## Migration Sequence

1. PR1064 established the common contract scaffold and drift guards.
2. PR1065 consolidated source-group authority without changing source lists.
3. PR1067 adapted existing batch RSS retrieval to return common evidence while preserving source order and budgets.
4. PR1069 persists common evidence through the canonical cache namespace and reuses prep evidence.
5. PR1069 migrates Ross READ_ONLY news retrieval to News Intelligence while keeping Ross catalyst qualification in scanner policy.
6. Additional strategies may migrate after Ross parity remains certified.

## PR1069 Safety Assertions

- NEWS INTELLIGENCE COMPLETION
- CANONICAL EVIDENCE/CACHE PATH COMPLETE
- PREP/OVERNIGHT EVIDENCE REUSED THROUGH NEWS INTELLIGENCE
- ROSS READ_ONLY NEWS RETRIEVAL MIGRATED TO NEWS INTELLIGENCE
- ROSS CATALYST QUALIFICATION REMAINS IN ROSS/SCANNER POLICY
- SOURCE LISTS AND ORDER UNCHANGED
- BOUNDED NEWS BUDGETS PRESERVED
- NO TIMEOUT INFLATION AS PRIMARY SOLUTION
- NO ROSS THRESHOLD CHANGE
- NO ROSS FIVE-PILLAR REDEFINITION
- ABSOLUTE VOLUME AND RVOL REMAIN DISTINCT
- NO CATALYST BYPASS
- NO PAPER
- NO LIVE
- ZERO BROKER ORDER MUTATIONS
- PAPER_READY=NO
- PAPER_READINESS_GATE=FAIL
