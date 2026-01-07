# IBKR Trading System

Algorithmic trading system using Interactive Brokers API.
Initial focus: momentum strategies inspired by Ross Cameron (paper trading only).

## Phase 13 — Signals Layer

Signals sit between the PatternEngine and StrategyRunner stages. The Signals
layer evaluates deterministic momentum triggers (HOD break, PMH break, micro
pullback, bull flag, ORB 1m) and emits teaching-first events without changing
strategy logic yet. Later phases will replace dict inputs with typed
CandleSeries + MarketSnapshot snapshots for real market structures.

New event types:
- SIGNAL_EMITTED
- SIGNAL_INVALID
