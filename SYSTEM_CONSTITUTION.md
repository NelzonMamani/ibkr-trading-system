## System Constitution (Excerpt)

### Execution Boundary Law
- Execution is a conditional subsystem.
- Execution code must never be a boot-time dependency.
- Execution modules must be lazy-loaded behind configuration guards.
- LIVE_READ_ONLY and SIM modes must function with execution entirely unavailable.

### AI Conduct Rule
Automated agents must:
- Read SYSTEM_CONSTITUTION.md
- Read SYSTEM_STATE.md
- Derive intent only from governance files and existing code
- Never guess intent
