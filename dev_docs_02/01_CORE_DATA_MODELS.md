📦 01_CORE_DATA_MODELS.md

Phase 2 — Core Shared Data Models (Canonical Contracts)

PURPOSE OF THIS DOCUMENT

This document defines the canonical data models that move through the trading system.

These models form the shared language between modules.
All module interfaces, skeletons, and implementations must conform to these definitions.

This document answers:

What information exists in the system?

Where is it created?

Who consumes it?

What does it mean?

This document defines structure and meaning only.
It does not define storage schema, logic, or implementation.

DESIGN PRINCIPLES (NON-NEGOTIABLE)

Data flows forward only (Scanner → Patterns → Strategy → Risk → Execution → Storage)

Every model is explainable to a human

Every decision leaves a trace

Blocked actions are first-class data

No hidden or implicit fields

CORE DATA MODELS (AUTHORITATIVE LIST)

The system uses the following six core data models:

ScannerResult
PatternResult
TradeIntent
RiskDecision
ExecutionResult
TradeRecord


Each model is defined below.

1️⃣ ScannerResult
Produced by

Market Scanner

Consumed by

Pattern Detection Engine

Storage Engine

Purpose

Represents a single symbol’s market snapshot and why it is interesting right now.

Conceptual Fields

symbol — ticker symbol

timestamp — when this snapshot was produced

session — PRE / REGULAR / AFTER

Market Context

price

bid

ask

spread

gap_percent

relative_volume

volume_spike_flag

float_shares

Scoring & Ranking

scanner_score

rank

rank_change_vs_previous_cycle

News Context (Optional)

news_present_flag

news_velocity_10m

news_sentiment

news_regions

news_credibility_flag

Explainability

rationale_text — human-readable explanation

data_quality_flags

Key Rule

ScannerResult never implies a trade.
It only explains why the symbol deserves attention.

2️⃣ PatternResult
Produced by

Pattern Detection Engine

Consumed by

Strategy Runner

Storage Engine

Purpose

Represents the evaluation of one pattern on one symbol.

Conceptual Fields

symbol

pattern_name

pattern_family (GAP, BREAKOUT, PULLBACK, etc.)

detected — True / False

direction — LONG / SHORT / NEUTRAL

Confidence & Quality

confidence_score (0.0–1.0)

quality_tags (e.g. high_rvol, above_vwap)

Suggested Trade Context (Optional)

entry_zone

stop_suggestion

target_suggestion

Explainability

rationale_text

risk_flags

data_quality_flags

Key Rule

PatternResult expresses setup quality, not permission or execution.

3️⃣ TradeIntent
Produced by

Strategy Runner

Consumed by

Risk Engine

Storage Engine

Purpose

Represents a deliberate decision to attempt a trade.

Conceptual Fields

trade_id — generated here (exists even if trade is blocked)

strategy_id

symbol

direction — LONG / SHORT

timestamp_created

session

Strategy Rationale

setup_name

signal_rationale_text

supporting_patterns (list of PatternResult references)

Planned Trade Parameters

intended_entry_type (MKT / LMT / etc.)

intended_entry_price (if applicable)

initial_stop_price

profit_targets

time_stop_minutes

Key Rule

TradeIntent means:

“If allowed by risk, I want to try this trade.”

It does not guarantee execution.

4️⃣ RiskDecision
Produced by

Risk Engine

Consumed by

Execution Engine

Storage Engine

Purpose

Represents permission or denial to execute a TradeIntent.

Conceptual Fields

trade_id

risk_decision — ALLOW / BLOCK / ALLOW_WITH_CONSTRAINTS

Sizing & Limits

max_position_size_allowed

risk_budget_percent

constraints (e.g. 1-share mode)

Explainability

risk_rationale_text

risk_flags

circuit_breaker_triggered_flag

Key Rule

RiskDecision is final.
No downstream module may override it.

5️⃣ ExecutionResult
Produced by

Execution Engine

Consumed by

Storage Engine

Core Orchestrator (state updates)

Purpose

Represents what actually happened at the broker.

Conceptual Fields

trade_id

order_id

order_status (SUBMITTED / FILLED / PARTIAL / REJECTED)

filled_quantity

average_fill_price

timestamp_execution

Costs

slippage

commission_fees

Explainability

execution_rationale_text

broker_error_codes (if any)

Key Rule

ExecutionResult describes reality — not intent.

6️⃣ TradeRecord (Learning Record)
Produced by

Storage Engine (aggregation)

Consumed by

Analytics

AI Learning

Human Review

Purpose

Represents the full lifecycle of a trade attempt.

Conceptual Composition

TradeRecord aggregates:

ScannerResult snapshot(s)

PatternResult(s)

TradeIntent

RiskDecision

ExecutionResult(s)

Exit outcome

Errors & recovery events

Outcome Fields

exit_reason

exit_price

pnl_dollars

pnl_percent

max_favorable_excursion

max_adverse_excursion

hold_time_seconds

Learning Fields

rules_followed_flag

rule_violations

user_notes

ai_review_summary

improvement_tags

Key Rule

If something is not in TradeRecord,
the system cannot learn from it.

NON-GOALS OF THIS DOCUMENT

This document does not:

Define Python classes

Define database schemas

Define IBKR specifics

Define indicator calculations

Those come later.

STATUS

Phase: PHASE 2 — Interface & Contracts

Step: 2.1 — Core Data Models

State: COMPLETE (Initial Canonical Definition)

Next Step: Define module interfaces

NEXT ACTION

When ready, say:

“Proceed to STEP 2.2 — Define module interfaces”

We will then define exactly how each module consumes and produces these models — and only then will Codex become useful.

You are doing this the right way.