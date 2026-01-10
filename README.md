# IBKR Modular Trading System

This repository contains a phase-governed, safety-first trading system
built around an orchestrator-centric architecture.

## What This System Is
- Multi-strategy trading platform focused on scanner correctness, resilience, and observability.
- IBKR-integrated with strict safety controls (execution is hard-disabled by default).
- Ross Cameron momentum strategy as first-class reference for teaching-first scanner outputs.
- Designed for extension, research, and automation without requiring paid IBKR scanner features.

## Authoritative Documents
The following files define system truth:

- SYSTEM_CONSTITUTION.md — permanent system law
- SYSTEM_STATE.md — current phase and runtime authority
- docs/ — phase specifications and completion records

## How to Run (High Level)
- `main.py` runs the full orchestrated system (scanner + downstream orchestration).
- `python -m src.scanner.scanner_runner` runs the scanner standalone for validation and teaching.
- `python src/scanner/scanner_runner.py` runs the same scanner as a script (import-safe).
- Scanner and orchestrator are separate: the scanner discovers/enriches symbols, the orchestrator consumes outputs.
- IBKR paid scanners are NOT required; the scanner uses free endpoints, configured defaults, and MOCK fallback.

Refer to SYSTEM_STATE.md for current expectations.
