# E17_STRATEGY_INTERACTION_RULES — CONFLICT RESOLUTION TASKS

Codex must:

1. Detect simultaneous intents on the same symbol
2. Classify conflict type (same / opposing direction)
3. Apply resolution hierarchy:
   - System safety (E15/E16)
   - Portfolio risk
   - Strategy priority
   - First-valid intent
4. Enforce resolution deterministically
5. Emit audit record

No strategy may cancel another directly.

END
