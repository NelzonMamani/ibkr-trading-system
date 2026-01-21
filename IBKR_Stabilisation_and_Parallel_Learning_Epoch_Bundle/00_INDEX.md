# BUNDLE INDEX — IBKR Trading System: Live Stabilisation + Observability + Parallel Learning Epoch

This zip contains **ordered Codex instruction documents**. Execute in numeric order.

## Order (Priority)
1. **01_FIX_LIVE_MICRO_SCANNER_READONLY_VIOLATION.md**
2. **02_SCANNER_OUTPUT_PRINTS_AND_WATCHLIST_LIFECYCLE.md**
3. **03_SYSTEM_HEALTH_DB_RECOVERY_CLEANUP_AND_GOVERNANCE.md**
4. **10_EPOCH_PARALLEL_LEARNING_GOVERNANCE.md**
5. **11_LEARNING_DATA_MODEL_STORAGE_AND_BACKFILL.md**
6. **12_REPORTING_ENGINE_DAILY_WEEKLY_MONTHLY_YEARLY.md**
7. **13_TRADE_REVIEW_AND_COACHING_FEEDBACK.md**
8. **14_POLICY_PROPOSAL_ENGINE_NO_AUTO_MUTATION.md**
9. **15_POLICY_COMPARISON_APPROVAL_AND_ACTIVATION_WORKFLOW.md**
10. **16_LEARNING_SCHEDULER_TRIGGERS_AND_RECOVERY.md**
11. **17_TESTS_SAFETY_BOUNDARIES_AND_VERIFICATION.md**
12. **99_MANDATORY_VERIFICATION_COMMANDS.md**

## Global invariant
- **Primary objective:** system can run **LIVE_MICRO safely** (1-share limit, max positions, max daily loss), using real IBKR market data, and can recover from interruption.
- **Learning is parallel:** it **never mutates live trading logic or baseline policies automatically**. It only produces **proposals** and **reports**.

## How to use
- Apply doc 01 → run the mandatory verification commands.
- Apply doc 02 → run the mandatory verification commands.
- Apply doc 03 → run the mandatory verification commands.
- Only then start doc 10+ learning epoch.

END
