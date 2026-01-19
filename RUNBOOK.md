# RUNBOOK — Epoch 5 Operations

## Canonical Run Commands (from repo root)

### Track A (Ross Momentum) — Orchestrator via `src.main`
```
python -m src.main --mode SIM --strategy ross_momentum --cycles 1
python -m src.main --mode READONLY --strategy ross_momentum --cycles 1
python -m src.main --mode PAPER --strategy ross_momentum --cycles 1
python -m src.main --mode LIVE_1SHARE --strategy ross_momentum --cycles 1
```

### Track B (Adaptive Regime Layer) — SIM / LIVE_READ_ONLY
SIM (policy off):
```
python -m src.main --mode SIM --strategy ross_momentum --cycles 1 --regime-layer
```

SIM (policy on):
```
python -m src.main --mode SIM --strategy ross_momentum --cycles 1 --regime-layer --regime-policy
```

LIVE_READ_ONLY (policy off):
```
python -m src.main --mode READONLY --strategy ross_momentum --cycles 1 --regime-layer
```

LIVE_READ_ONLY (policy on):
```
python -m src.main --mode READONLY --strategy ross_momentum --cycles 1 --regime-layer --regime-policy
```

### Doctor / Bootstrap (READONLY scanner validation)
```
python -m src.core_engine.doctor
```

### Scanner Standalone (READONLY, single cycle)
```
python -m src.scanner.scanner_runner --mode READONLY --cycles 1
```

### Orchestrator (SIM)
```
python -m src.core_engine.orchestrator --mode SIM --cycles 1
```

### Orchestrator (READONLY)
```
python -m src.core_engine.orchestrator --mode READONLY --cycles 1
```

### Orchestrator (LIVE_1SHARE) — Safety Warning
LIVE_1SHARE submits orders only when explicitly enabled and risk-approved.
Ensure IBKR connectivity and confirm all safety flags before running:
```
python -m src.core_engine.orchestrator --mode LIVE_1SHARE --cycles 1
```

## Troubleshooting
- **Import errors**: run `python -c "import src"` to verify package visibility.
- **Scanner empty**: empty watchlists are valid; verify drop reasons in console output.
- **IBKR connection**: READONLY/SIM do not require IBKR; LIVE_1SHARE expects a configured gateway.
