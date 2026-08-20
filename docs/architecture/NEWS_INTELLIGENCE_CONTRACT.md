# News Intelligence Contract

## Purpose

This document defines the strategy-agnostic News Intelligence contract scaffold introduced for PR1064. It is a contract and interface spine only. It does not change production scanner behavior, news retrieval behavior, source coverage, cache behavior, Ross thresholds, PAPER authority, LIVE authority, or broker-order authority.

## Ownership Boundary

News Intelligence owns objective news evidence: source retrieval facts, normalized article facts, entity matches, freshness, reliability, heat, velocity, cache state, and retrieval availability.

Strategies own interpretation. Ross may later consume News Intelligence through a Ross adapter, but common news code must not import `src.strategies.ross_momentum` and must not encode Ross trading decisions or thresholds.

Dependency direction:

```text
News Intelligence
        ^
        |
Strategy adapter / strategy policy
```

## WHAT vs WHERE

`NewsRequest` describes WHAT evidence a consumer asks for: strategy identity, event classes, freshness/lookback windows, generic-news inclusion, heat, velocity, reliability, result limits, session phase, and audit reason.

`RetrievalPolicy` describes WHERE and HOW evidence may be obtained: source groups, provider groups, cache read/write permission, refresh mode, network permission, total and tier budgets, timeout policy, fallback mode, and source/item limits.

The common contract does not put Ross price, gap, float, volume, RVOL, session, pattern, entry, stop, or target thresholds into either object.

## Batch-First Model

`NewsIntelligenceProvider.get_news(candidates, request, retrieval_policy)` is batch-first and returns `NewsBatchResult`. A single-symbol lookup is represented as a batch of one. This preserves the intended architecture where a provider can fetch each source once, parse once, and match many symbols.

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

## Strategy Neutrality

`NewsEvidenceSummary` is a latency-friendly per-symbol summary, not a trading decision. It can expose evidence counts, fresh evidence counts, qualifying event-class counts, generic evidence counts, freshest age, reliability, heat, velocity, source counts, retrieval status, provider status, cache state, budget exhaustion, and diagnostics.

It must not expose Ross decisions such as buy/pass/A-quality labels, and it must not treat retrieval unavailable or budget exhaustion as "no catalyst."

## Preparation vs Active Scanner Direction

Future preparation or closed-market work should perform broader bounded collection, normalization, classification, cache persistence, and evidence summarization where session policy allows.

Future active scanner work should read valid prepared/cached evidence first, then perform bounded incremental updates for unresolved or high-priority symbols. It should not search the complete historical RSS catalogue every scanner cycle.

PR1064 does not implement that migration.

## Volume vs RVOL

Absolute share volume and Relative Volume/RVOL are distinct upstream concepts. `NewsCandidate` may carry `absolute_share_volume` and `relative_volume_rvol` for prioritization or audit context, but News Intelligence does not calculate either value and is not the authority for either value.

This preserves the Ross contract: Price, Gap / percentage move, Float, Volume, and News / catalyst remain the five stock-selection pillars, while RVOL remains a supporting metric.

## Migration Sequence

1. Establish this common contract scaffold and drift guards.
2. Consolidate source-group authority without changing source lists.
3. Adapt existing batch RSS retrieval to return common evidence while preserving behavior.
4. Persist common evidence through existing prep/cache authority.
5. Add a Ross adapter that interprets common evidence through Ross catalyst policy.
6. Migrate additional strategies after Ross parity is certified.

## PR1064 Safety Assertions

- CONTRACT/SCAFFOLD ONLY
- NO PRODUCTION NEWS RETRIEVAL BEHAVIOR CHANGE
- NO ROSS THRESHOLD CHANGE
- NO ROSS FIVE-PILLAR REDEFINITION
- ABSOLUTE VOLUME AND RVOL REMAIN DISTINCT
- NO CATALYST BYPASS
- NO PAPER
- NO LIVE
- ZERO BROKER ORDER MUTATIONS
- PAPER_READY=NO
- PAPER_READINESS_GATE=FAIL
