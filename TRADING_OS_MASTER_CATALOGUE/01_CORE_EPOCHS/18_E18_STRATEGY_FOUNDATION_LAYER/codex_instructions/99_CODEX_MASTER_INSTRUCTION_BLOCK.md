# E18_STRATEGY_FOUNDATION_LAYER — CODEX MASTER INSTRUCTION (COPY/PASTE)

FILE: 99_CODEX_MASTER_INSTRUCTION_BLOCK.md
TITLE: E18_STRATEGY_FOUNDATION_LAYER — CODEX MASTER INSTRUCTION

Codex, you must implement Epoch E18 strictly according to the governance bundle located at:
TRADING_OS_MASTER_CATALOGUE/01_CORE_EPOCHS/18_E18_STRATEGY_FOUNDATION_LAYER/governance/

PROCESS (MANDATORY):
1) READ governance bundle fully (all files in read order).
2) READ this CODEX bundle fully (all files in read order).
3) REALITY CERTIFY:
   - Create REALITY_MAP_E18.md as specified.
   - Do not implement before reality map exists.
4) GAP ANALYSE:
   - For each governance checklist item, mark implemented/missing.
   - Propose minimal additive changes.
5) IMPLEMENT (ADDITIVE ONLY):
   - Add semantic contracts and registries for SF/XL/C/K and candlestick primitives.
   - Implement missing items with deterministic, testable modules.
   - Add Levels/Zones primitives, structure states, invalidation contract.
   - Add Symbol Commitment + Context Hydrator with completeness flags and HAS_NEWS boolean.
   - Add lifecycle classification and reset (soft/hard/version) for foundation-generated caches.
   - Add translation/coverage/drift report generator and deterministic outputs.
   - Add foundation completeness proof command/check.
6) TEST:
   - Create deterministic unit tests for all new primitives (no live IBKR dependency).
7) VERIFY:
   - Run ALL mandatory verification commands in 15_MANDATORY_VERIFICATION_COMMANDS.md
   - Fix failures until all pass.
8) AUDIT OUTPUT:
   - Append an E18_PR_VERIFICATION_REPORT.md in the epoch folder describing what changed,
     what was missing, and proof of checklist completion.
9) STOP when all verification passes and E18 success criteria are met.

HARD RULES:
- No refactors, no renames, no architecture rewrites.
- No new run modes.
- Do not modify strategy policies to fit the foundation.
- Do not embed Ross-only assumptions as global gates.
- All checklist items are binary: missing item = FAIL.

END
