Configuration_Wiring­_Audit.md
? Codex Instruction — Configuration Wiring Audit (READ-ONLY)
Task type: READ-ONLY CODE ANALYSIS
Do NOT modify any files. Do NOT suggest code changes.
Please analyse the current repository and answer the following only by referencing existing code:

1. Configuration Variables Inventory
For each of the following configuration concepts, identify:
Where the variable is defined
Where it is read
Where it is enforced
Whether it is unused, partially used, or fully wired
Concepts to trace:
RunMode (SIM / PAPER / LIVE / LIVE_READ_ONLY / LIVE_MICRO)
IBKR_READONLY_ENABLED
SCANNER_MODE
IBKR_MARKET_DATA_TYPE
IBKR_MAX_SYMBOLS_PER_CYCLE
SCANNER_SYMBOLS
INTENT_DEDUP_SELFTEST_ENABLED

2. Scanner Behaviour Wiring
Please explain:
What currently determines whether the scanner runs in teaching mode vs live data
Whether SCANNER_MODE affects scanner logic at runtime
If not, where scanner behaviour is hard-coded

3. Execution Safety Wiring
Explain how the system prevents:
Order submission in SIM
Order submission when IBKR_READONLY_ENABLED=True
Accidental execution in LIVE
Identify the exact files and guards responsible.

4. Mode Transition Readiness
Based on existing code (without modification):
What would need to be changed by configuration only to move from:
SIM → PAPER
PAPER → LIVE_READ_ONLY
LIVE_READ_ONLY → LIVE
If this is not possible, state why and where the gap is.

5. Dead or Incomplete Configuration Paths
Identify any configuration variables that:
Are defined but never used
Are read but never enforced
Appear to be placeholders for future phases

Output format:
Structured sections
File paths
Line references where possible
No code edits
No refactors
Important: This is an audit, not an implementation task.
