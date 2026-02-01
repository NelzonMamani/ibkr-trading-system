# 06_MANDATORY_VERIFICATION_COMMANDS.md
TITLE: Mandatory Verification Commands — Must Pass Before Codex Stops
DATE: 2026-01-31

Codex must run these locally (or in CI if available). If any fail, Codex must fix and re-run until all pass.

## 1. Repository sanity
```bash
git status
python -V
```

## 2. Lint/compile (minimum)
```bash
python -m compileall -q src
```

## 3. Unit tests (if present)
```bash
pytest -q
```
If there are no tests or coverage is insufficient for the new behavior, Codex must add tests for:
- session derivation
- reference price labeling
- risk profile resolution + enforcement
- paper execution lifecycle
- at least one representative Ross setup per family group

## 4. Smoke runs (authoritative)
### 4.a PAPER end-to-end (1 cycle)
```bash
python -m src.main --mode PAPER --cycles 1 --strategy ross_momentum
```

### 4.b LIVE_READ_ONLY scan-only (1 cycle)
```bash
python -m src.main --mode LIVE_READ_ONLY --cycles 1 --strategy ross_momentum
```

### 4.c CLOSED-mode prep (simulate weekend)
If the system supports a “time travel” / override clock, run it.
Otherwise, create a deterministic harness command:
```bash
python -m src.verification.paper_harness --scenario closed_weekend_prep
```

### 4.d Risk profile MICRO clamp check
```bash
python -m src.verification.paper_harness --scenario micro_profile_trade
```
Expected:
- order intents show desired size
- executed size clamped to 1 share
- adds rejected/blocked when scaling disabled

## 5. Strategy completeness checks
Codex must add a script to enumerate registered Ross setups and assert none missing:
```bash
python -m src.verification.verify_ross_setups_complete
```

END
