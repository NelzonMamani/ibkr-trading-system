# E17_STRATEGY_INTERACTION_RULES — REQUIRED CONTRACTS

Codex must ensure the following interaction contracts exist:

1. Strategy Identity Contract
   - Unique strategy_id
   - Strategy class (intraday, swing, long-horizon)

2. Intent Declaration Contract
   - Entry / exit intent
   - Symbol, direction, size request

3. Position Ownership Contract
   - One active owner per symbol per direction

4. Priority Declaration Contract
   - Strategy priority class

Implicit interaction is forbidden.

END
