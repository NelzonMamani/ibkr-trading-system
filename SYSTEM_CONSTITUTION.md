# SYSTEM CONSTITUTION
## IBKR Modular Trading System

### 1. System Identity
This repository defines a professional-grade, modular, multi-strategy trading platform.
The first-class, reference strategy is Ross Cameron–style momentum trading, but the
architecture MUST support additional strategies (quantitative, algorithmic, mean-reversion,
scalping, etc.) without redesign.

The system is orchestrator-centric and phase-governed.

### 2. Safety Is Non-Negotiable
- Execution is NEVER allowed unless explicitly enabled by configuration.
- LIVE_READ_ONLY mode MUST NEVER route orders.
- Scanner modules are intelligence-only and may not submit trades.
- All LIVE modes must degrade safely on data or connectivity failure.
- MOCK fallback is mandatory when IBKR or external data is unavailable.

### 3. Data Trust & Provenance Policy
- Market data priority: IBKR → MOCK (fallback).
- News data is advisory, probabilistic, and non-blocking.
- verified_rss.txt is the ONLY authoritative list of permitted RSS sources.
- News unavailability must NEVER crash the scanner.
- Trust is separate from availability.

### 4. Phase Authority Model
- The system advances through explicit phases.
- A phase is complete only when its acceptance criteria are met.
- No partial or implicit phase transitions are allowed.
- Phase documents are authoritative over code when ambiguity exists.

### 5. AI & Automation Conduct Rules
- Automated agents (Codex, AI tools) must read this document before changes.
- Guessing system intent is forbidden.
- All assumptions must be logged or documented.
- Changes must align with current SYSTEM_STATE.md.

This document changes rarely and defines permanent system law.
