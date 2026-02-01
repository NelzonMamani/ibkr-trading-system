# 10_99_CODEX_MASTER_INSTRUCTION_BLOCK.md — CODEX MASTER INSTRUCTION (COPY/PASTE)

FILE: 10_99_CODEX_MASTER_INSTRUCTION_BLOCK.md
TITLE: Long Horizon Value (Buffett) — Phase-by-Phase Implementation Instructions

You are Codex working in the repository `ibkr-trading-system`.

CONTEXT:
- The Long Horizon Value strategy code exists at:
  `src/strategies/long_horizon_value/`
- Governance bundle exists at:
  `for_long_horizon_value/EPOCH_LONG_HORIZON_VALUE_GOVERNANCE/`
- Current repo work-in-flight includes scanner/Ross/modes fixes. You MUST NOT interfere with those areas unless
  a failing verification requires a minimal, targeted fix that is directly caused by your work.

NON-NEGOTIABLE RULES:
1) Do NOT modify `src/strategies/long_horizon_value/strategy_policy.py` except for import/path fixes.
2) Do NOT add intraday scanner dependencies. This strategy is fundamentals-only.
3) Do NOT bypass Risk Engine or Execution authority. Emit TradeIntents only.
4) Implement in order per 10_00_EXECUTION_ORDER.md. No parallelisation.
5) After each phase, run ALL commands in 10_90_MANDATORY_VERIFICATION_COMMANDS.md.
   If any fail: fix and re-run until green, then proceed.

WORK PLAN:
- Read and follow documents in 00_READ_ORDER.md.
- Implement Phase 00 through Phase 10 one by one using the corresponding 10_XX documents.
- Add tests as requested.
- Ensure the strategy runs in SIM and PAPER and produces reports + intents, with no execution leakage.
- Stop when all mandatory verification passes.

DELIVERABLES:
- Phase-complete implementation
- Tests passing
- Logs stored under `output/verification/`
- Clear PR with summary of what changed and why

END
