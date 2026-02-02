# Risk & Position Management (Governance)

## Mandatory constraints
- Every intent must include a **hard stop** and **predefined target**
- If computed R:R < minimum → no trade
- If stop is too wide in ATR terms → no trade

## No averaging down (immutable)
This strategy does not average down into a loser.

## Risk engine interface
Risk engine is allowed to veto or constrain sizing.
Risk engine is not allowed to create trades or remove stop/target requirements.
