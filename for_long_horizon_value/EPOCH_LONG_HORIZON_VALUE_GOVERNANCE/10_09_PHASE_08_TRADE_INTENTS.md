# 10_09_PHASE_08_TRADE_INTENTS.md — PHASE 08: TRADE INTENT GENERATION

Goal:
- Create TradeIntents (never direct execution).
- Intent state must encode approval/capital gating.

Codex tasks:
1) For BUY_READY symbols:
   - create TradeIntent with target_pct and max_price
   - set state:
     - AWAITING_APPROVAL if REQUIRE_MANUAL_APPROVAL True
     - READY if automation allowed
2) For Focus symbols blocked by capital:
   - optionally create TradeIntent with state BLOCKED_CAPITAL (non-executable)
3) Ensure intents flow through existing intent/risk/execution pipeline WITHOUT bypass.
4) Emit operator-facing report:
   - Checklist summary per symbol, including numeric layer scores and MoS.

Tests:
- TradeIntent schema compliance.
- No intents in disallowed cadence windows.
- In LIVE_READ_ONLY, intents must never result in execution calls.

END
