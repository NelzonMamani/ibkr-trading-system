# Context & Objectives

This document formalises the final alignment decisions for the IBKR Trading System.

Objectives:
- Ensure the system trades when valid opportunities exist.
- Eliminate silent failures and ambiguity.
- Make the scanner observable and event-driven.
- Introduce a background pre-market preparation layer.
- Preserve fast execution even without preparation.

Non-negotiable principles:
- Scanner emits facts, never decisions.
- Orchestrator is event-driven.
- Strategy owns all trade decisions.