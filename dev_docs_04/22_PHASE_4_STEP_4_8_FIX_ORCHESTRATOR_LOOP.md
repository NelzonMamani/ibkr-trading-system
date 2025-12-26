📘 CONTENT
Title

Fix Orchestrator: Loop TradeIntents into RiskEngine (Phase 4.8 Alignment)

Problem Summary

The RiskEngine correctly expects a single TradeIntent, but the CoreOrchestrator passed a list. This caused an AttributeError when accessing trade_intent.symbol.

Correct Responsibility

StrategyRunner returns List[TradeIntent]

CoreOrchestrator loops over them

RiskEngine evaluates one TradeIntent at a time

Codex Instruction (COPY EXACTLY)
ROLE:
You are acting as a careful Python engineer.

PHASE:
PHASE 4 — Minimal Live-Capable System

LOCAL OBJECTIVE:
Fix CoreOrchestrator so it loops over TradeIntent objects
and sends them one-by-one to the RiskEngine.

ALLOWED FILE TO MODIFY:
- src/core/orchestrator.py

REQUIREMENTS:
1. In run_once(), treat strategy_output as List[TradeIntent].
2. For each TradeIntent:
   - Call risk_engine.evaluate_trade_intent(trade_intent)
   - Collect RiskDecision objects into a list.
3. Add teaching logs:
   - How many trade intents are being risk-evaluated
   - Which symbol is currently being evaluated
4. Do NOT modify RiskEngine.
5. Do NOT change data models.
6. Preserve all existing teaching logs.

FORBIDDEN:
- No logic changes in risk_engine.py
- No conditional blocking
- No execution logic

OUTPUT FORMAT:
- Output FULL FILE CONTENTS only
- NO diff format
- NO + / - lines

What You Should See After the Fix

Expected logs (example):

[RISK] Beginning risk evaluation for 3 trade intents
[RISK] Evaluating TradeIntent for symbol=ABC
[RISK] Allowed=True | Max size=1 | Risk level=LOW
[RISK] Evaluating TradeIntent for symbol=XYZ
[RISK] Allowed=True | Max size=1 | Risk level=MEDIUM
[RISK] Evaluating TradeIntent for symbol=LMN
[RISK] Allowed=True | Max size=1 | Risk level=LOW


And your TradeRecord will now contain:

scanner_output   ✅
pattern_output   ✅
strategy_output  ✅
risk_output      ✅ (List[RiskDecision])
execution_output ⬜

Why This Is a Milestone

This error confirms:

Your data contracts are real

Your modules are independent

Your orchestrator is the traffic controller

You are now officially in multi-trade-capable architecture

This is exactly how professional systems are built.

Next Step (After Fix)

👉 STEP 4.9 — Execution Engine (SIM Orders Only)
We will convert RiskDecision → ExecutionResult (still no broker).

Say when ready and I’ll give you the next file with filename first, as requested.