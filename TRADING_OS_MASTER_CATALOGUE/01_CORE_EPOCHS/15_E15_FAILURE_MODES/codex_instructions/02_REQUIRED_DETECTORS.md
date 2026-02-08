# E15_FAILURE_MODES — REQUIRED DETECTORS

Codex must ensure the following detectors exist and are wired:

1. Data Freshness Detector
   - Verifies timestamp monotonicity
   - Detects frozen market data

2. Session Authority Detector
   - PRE / RTH / AH / CLOSED awareness
   - Prevents session-misaligned decisions

3. Run Mode Authority Detector
   - Ensures RUN_MODE ∈ {SIM, PAPER, READ_ONLY, LIVE}
   - Forbids size-based modes

4. Execution Permission Detector
   - Execution allowed ONLY when RUN_MODE == LIVE
   - Execution disabled immediately otherwise

5. Database Health Detector
   - Writable DB
   - Size thresholds
   - Lock detection

All detectors must return explicit GREEN / RED states.

END
