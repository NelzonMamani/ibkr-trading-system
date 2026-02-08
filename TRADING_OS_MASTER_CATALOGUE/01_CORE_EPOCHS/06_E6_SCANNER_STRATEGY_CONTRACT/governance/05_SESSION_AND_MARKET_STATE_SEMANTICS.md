## Session & Market State Semantics

Scanner behavior must be explicit for:
- PRE market
- Regular Trading Hours (RTH)
- After Hours (AH)
- CLOSED (weekends / holidays)

Rules:
- Reference prices must be declared per session
- % change semantics must match IBKR session logic
- CLOSED mode may still produce prep artifacts
- No silent N/A propagation without flags
