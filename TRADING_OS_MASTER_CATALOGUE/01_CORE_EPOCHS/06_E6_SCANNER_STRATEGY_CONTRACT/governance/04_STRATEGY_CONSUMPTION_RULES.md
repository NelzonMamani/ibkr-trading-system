## Strategy Consumption Rules

Strategies:
- Consume scanner output as **input facts**
- Apply all ranking, gating, exclusions internally
- Must tolerate empty scanner outputs
- Must log why symbols are accepted/rejected

No strategy may require scanner changes to evolve logic.
