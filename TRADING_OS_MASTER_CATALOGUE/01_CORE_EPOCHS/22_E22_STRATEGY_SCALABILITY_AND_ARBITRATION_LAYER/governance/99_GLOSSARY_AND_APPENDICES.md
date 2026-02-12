
# Glossary and Appendices

## Terms
- **Intent**: a proposed trading action (buy/sell/exit/modify) produced by a strategy.
- **Arbitration**: deterministic selection and suppression process producing final intents.
- **Budget**: hard cap on external requests and compute time.
- **Coordinator**: shared data layer that coalesces/caches requests.

## Appendix A — Example arbitration ordering
Primary sort keys (example):
1) strategy priority (desc)
2) intent type priority (EXIT > REDUCE > ENTRY)
3) confidence (desc)
4) liquidity score (desc)
5) stable hash(strategy_key + symbol + side) (asc)

## Appendix B — Example suppression payload
```json
{
  "strategy_key": "ross_momentum",
  "symbol": "XYZ",
  "intent_id": "abc",
  "reason_code": "SYMBOL_EXCLUSIVITY_CONFLICT",
  "winner": {"strategy_key": "mean_reversion", "intent_id": "def"},
  "context": {"policy": "symbol_exclusive", "tie_break": "priority_then_hash"}
}
```
