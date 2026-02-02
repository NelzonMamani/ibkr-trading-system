# Decision Workflow Algorithm (Authoritative)

This document describes the algorithmic workflow at the strategy level.
It is intended to be implementable without interpretation.

## High-level loop (per cycle)
1. Receive a list of symbols (watchlist/focus) and ScannerFacts for each symbol.
2. Compute / receive MarketRegimeFacts once per cycle.
3. For each symbol:
   1) Validate price/sanity
   2) Regime approval gate (Clause 7)
   3) Liquidity gate (spread/quality) (supporting)
   4) ATR availability gate (supporting)
   5) Select mean (Clause 3)
   6) Compute extension from mean (Clause 1)
   7) Determine side (above mean → SHORT; below mean → LONG)
   8) Exhaustion / continuation failure (Clause 2)
   9) Determine setup label (optional, for audit)
   10) Determine confirmed entry (Clause 4)
   11) Compute stop (Clause 5)
   12) Compute target (Clause 6)
   13) Compute R:R and validate asymmetry (Clause 8)
   14) Emit TradeIntent if allowed; otherwise emit no-trade reason

## Detailed pseudo-code (exact intent)
```text
for each cycle:
    regime = get_market_regime_facts()

    for each symbol in symbols:
        facts = get_scanner_facts(symbol)

        if invalid_symbol_or_price(facts): deny(INVALID_PRICE_OR_SYMBOL)

        if not regime_permission(facts, regime): deny(<REASON>)

        if not liquidity_ok(facts): deny(SPREAD_TOO_WIDE or ...)

        if atr_missing_or_small(facts): deny(NO_VALID_ATR)

        mean, mean_name = select_mean(facts)
        if mean missing: deny(NO_VALID_MEAN_REFERENCE)

        ext_atr = abs(last - mean) / atr
        if ext_atr < min_ext: deny(NOT_OVEREXTENDED)
        if ext_atr > max_ext: deny(EXTENSION_TOO_EXTREME_UNSTABLE)

        side = SHORT if last > mean else LONG

        ok, score = exhaustion_gate(facts, side)
        if not ok: deny(EXHAUSTION_FAIL:...)

        setup = classify_setup(facts, side, mean_name)

        entry_type, entry_price = structural_entry(facts, side, atr, setup)
        if none: deny(NO_STRUCTURAL_ENTRY)

        stop = compute_stop(facts, side, atr, setup)
        if invalid: deny(INVALID_STOP_PRICE)
        if stop_distance/atr > max_stop_atr: deny(STOP_TOO_WIDE)

        target = compute_target(mean, side, atr)
        if invalid: deny(INVALID_TARGET_PRICE)

        rr = target_distance / stop_distance
        if rr < min_rr: deny(INSUFFICIENT_RR)

        intent = build_trade_intent(symbol, side, entry_type, entry_price, stop, target)
        if risk_engine_veto(intent): deny(RISK_ENGINE_VETO:...)

        approve(intent, diagnostics)
```
