# SYSTEM_CONSTITUTION
This document is the permanent system law for the IBKR Modular Trading System.
It defines non-negotiable safety, architecture, and governance principles.

## 1) System Purpose
Build a modular, orchestrator-centric trading system that supports multiple strategies
(momentum, quant, mean reversion, scalping, etc.) without redesign.

## 2) Phase Governance Is Mandatory
- The system advances through explicit phases.
- A phase is complete only when its acceptance criteria are met.
- No partial or implicit phase transitions are allowed.

## 3) Safety Is Non-Negotiable
- Execution is NEVER allowed unless explicitly enabled by configuration.
- LIVE_READ_ONLY mode MUST NEVER route orders.
- Scanner modules are intelligence-only and may not submit trades.
- All LIVE modes must degrade safely on data or connectivity failure.
- MOCK fallback is mandatory when IBKR or external data is unavailable.

## 4) Orchestrator & Scanner Roles
- The orchestrator is the authority for lifecycle, logging cadence, and phase gating.
- Scanner output is advisory intelligence only, never an execution trigger.
- Scanner must produce canonical output regardless of news or broker availability.

## 5) Data Trust & Provenance Policy
- Market data priority: IBKR → MOCK (fallback).
- Paid IBKR scanner subscriptions are not required or assumed.
- News data is advisory, probabilistic, and non-blocking.
- `verified_rss.txt` at repo root is the ONLY authoritative list of permitted RSS sources.
- News unavailability must NEVER crash the scanner.

## 6) Import Hygiene & Startup Integrity (Non-Negotiable)
- The system must be runnable via module execution:
  - `python -m src.main`
  - `python -m src.scanner.scanner_runner`
- No execution-layer import (brokers/execution/routing) may prevent orchestrator startup
  when execution is disabled by configuration.
- No `sys.path` hacks for production paths. Fix imports at the package level.

## 7) Teaching-First & No Silent Failures
- Teaching-first: degradations must be explicit and explainable.
- No silent failures: missing data must produce explicit logs and file headers.
- Configuration mismatches must be surfaced in console output.

## 8) Logging & Configuration Authority
- Configuration is resolved by `src/config/` (resolver + registry) and is authoritative.
- Configuration sources (ENV/DEFAULT/OVERRIDE) must be logged for key caps.
- Logging must be human-readable, concise, and summary-first.

## 9) AI & Automation Conduct Rules
Automated agents (Codex, AI tools) must derive intent ONLY from:
- `SYSTEM_CONSTITUTION.md`
- `SYSTEM_STATE.md`
- `README.md`
- Existing code behavior

Guessing system intent is forbidden. Assumptions must be documented.
