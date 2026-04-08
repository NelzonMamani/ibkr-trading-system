FILE: CODEX_E27_ROSS_POLICY_CONSUMER.md
TITLE: IMPLEMENT ROSS AS FIRST E27 EXECUTION POLICY CONSUMER
END MARKER: END_OF_CODEX_INSTRUCTION

MISSION

Implement Ross as the first consumer of E27 through a shared ExecutionPolicy adapter.

Ross-specific policy requirements:

1. ENTRY
- 10-second micro pullback breakout
- volume confirmation
- no entry directly into major level

2. INITIAL STOP
- pullback low minus buffer

3. FIRST TARGET
- nearest of:
  - half / whole dollar
  - HOD / breakout level
  - 2R if it lands earlier

4. BREAKEVEN
- default move to breakeven at 1R

5. PARTIAL
- partial at first target

6. TRAIL
- structure-based higher-low trail

7. RED VOLUME
Use thresholds:
- >=0.7 = no new entry
- >=1.0 = exit
- >=1.5 = hard exit + pause

8. GREEN VOLUME
Use thresholds:
- >=1.2 = strong
- >=1.5 = scale candidate
- >=2.0 = aggressive continuation

9. RETRACE
- >50% 1-minute retrace before close = immediate exit + pause

10. LEVELS
Must explicitly incorporate:
- whole dollars
- half dollars
- HOD
- premarket high
- breakout level

---

REQUIRED OUTPUT

Create Ross policy implementation so E27 can call policy methods and produce deterministic decisions without embedding Ross-specific lifecycle code into generic execution components.

END_OF_CODEX_INSTRUCTION
