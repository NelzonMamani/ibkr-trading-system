# Background Pre-Market Preparation Engine

Purpose:
Prepare expensive or slow-to-fetch data *before* it is needed.

## Inputs
- Extended scanner universe (e.g. top 150)
- Symbols from momentum spike events

## Cached Data
- Float (weekly refresh)
- News (≤ 6 hours old)
- Daily levels (20/50/200 EMA, VWAP anchors)
- Prior day H/L, gap context

## Retention Rules
- News expires after 6 hours
- Float expires weekly
- Technical levels expire after 48 hours
- Full reset every Friday evening

## Output
- PREP_UPDATED events
- Read-only symbol preparation cache

Preparation must never block live execution.