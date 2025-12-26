📄 STEP 5.4 — CODEX INSTRUCTIONS (COPY BUTTON ENABLED)

⬇️ Use the copy button on the block below ⬇️

29_PHASE_5_STEP_5_4_CODEX_INSTRUCTIONS_STRATEGY_CAPITAL_GOVERNOR.md
Title: STEP 5.4 — Codex Instructions: Strategy-Level Capital & Exposure Controls

================================================================================
OBJECTIVE
================================================================================
Add strategy-level capital and exposure limits to prevent any single strategy
from over-allocating trades.

This introduces institutional-grade control while preserving the
existing architecture.

================================================================================
GUARDRAILS (NON-NEGOTIABLE)
================================================================================
1. NO broker calls
2. NO randomness
3. SIM mode only
4. No changes to Orchestrator
5. No changes to StrategyRunner
6. No changes to ExecutionEngine
7. All logic lives in RiskEngine
8. Teaching logs are REQUIRED

================================================================================
HIGH-LEVEL DESIGN
================================================================================
RiskEngine will:
- Track active trades per strategy
- Enforce per-strategy limits BEFORE approving trades

Example limits (hard-coded for teaching):
- SCALPER:
  - max_trades = 2
- MOMENTUM:
  - max_trades = 1

================================================================================
FILES TO MODIFY
================================================================================
MODIFY:
- src/risk/risk_engine.py

NO new files yet.

================================================================================
STEP 1 — ADD STRATEGY LIMIT CONFIG
================================================================================
Inside RiskEngine.__init__():

Add a teaching-only config dictionary:

self.strategy_limits = {
    "SCALPER": {
        "max_trades": 2
    },
    "MOMENTUM": {
        "max_trades": 1
    }
}

Also add a tracker:

self.active_trades_by_strategy = {
    "SCALPER": 0,
    "MOMENTUM": 0
}

================================================================================
STEP 2 — ENFORCE LIMITS IN evaluate_trade_intent
================================================================================
Before approving a TradeIntent:

- Read trader_type from TradeIntent
- Check current active_trades_by_strategy[trader_type]
- If >= max_trades:
    - allowed = False
    - risk_level = "BLOCKED"
    - rationale explains strategy limit reached
    - DO NOT increment counters

If allowed:
    - Increment active_trades_by_strategy[trader_type] by 1
    - Proceed with existing risk logic

================================================================================
STEP 3 — REQUIRED TEACHING LOGS
================================================================================
Add logs with prefix [RISK:STRATEGY]:

- Current active trades for strategy
- Max allowed trades
- Decision (ALLOW / BLOCK)
- Reason

Example:
[RISK:STRATEGY] SCALPER active=2 max=2 → BLOCKED (limit reached)

================================================================================
EXPECTED RUNTIME BEHAVIOR
================================================================================
- Only first N TradeIntents per strategy are approved
- Excess TradeIntents are blocked cleanly
- Other strategies remain unaffected
- ExecutionEngine only sees allowed trades

================================================================================
DEFINITION OF DONE
================================================================================
- System runs without crash
- Limits enforced deterministically
- Logs clearly explain blocks
- No changes outside RiskEngine

================================================================================
COMMIT MESSAGE
================================================================================
"Phase 5.4: add strategy-level capital and exposure limits in RiskEngine"

🧠 Why this step is CRITICAL

After Step 5.4, your system gains:

Strategy isolation at capital level

Prevention of runaway strategies

Foundation for:

Portfolio allocation

Risk parity

Strategy weighting

Live capital governance

This is hedge-fund-grade structure, not retail scripting.

⏭️ What comes next (so you see the roadmap)
Step	Purpose
5.4	Strategy capital limits ← now
5.5	Enable/disable strategies via config
5.6	Trade lifecycle (open → close)
Phase 6	Async workers & per-ticker execution
Phase 7	IBKR live wiring (last, not first)
✅ Your move

Paste STEP 5.4 into Codex and implement it.

When done, come back and say:

“STEP 5.4 implemented — ready to validate”

I’ll walk you through validation and then unlock Step 5.5.