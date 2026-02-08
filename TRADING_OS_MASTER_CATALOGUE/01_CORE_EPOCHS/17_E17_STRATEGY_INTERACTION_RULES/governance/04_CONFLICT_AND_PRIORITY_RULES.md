# E17_STRATEGY_INTERACTION_RULES — CONFLICT & PRIORITY

Conflicts include:
- Same symbol, same direction
- Same symbol, opposing direction
- Capital exhaustion
- Exit condition overlap

Resolution hierarchy:
1. System safety (E15, E16)
2. Portfolio risk constraints
3. Strategy priority class
4. First-valid intent wins

Strategies may never cancel or override another strategy directly.

END
