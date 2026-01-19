# Phase 24 — Configuration Authority

This document explains why configuration is centralized and enforced.

## Why this exists

Configuration is now resolved through a single registry and resolver to eliminate
implicit defaults, hidden environment dependencies, and runtime ambiguity.

## What changed

* **Registry size:** 116 variables
* **HARD enforced:** 27
* **SOFT:** 80
* **ADVISORY:** 9

## How ambiguity was eliminated

* All modules read configuration via `get_config` and the resolver.
* Environment variables are parsed once and validated for type/constraints.
* Derived values (e.g. effective run mode) are explicitly recorded.
* A structured CONFIG_RESOLVED event is emitted at startup.

## Future extension pattern

1. Add a new entry to `CONFIG_REGISTRY` with type, default, env overrides, and metadata.
2. Add enforcement rules or validation in `config_resolver` if needed.
3. Regenerate documentation by running the config docs generator.

## Scanner authority (Ross Momentum)

* Stock selection thresholds now live in `RossMomentumPolicy.stock_selection`.
* The orchestrator loads the strategy policy and delegates that stock selection policy to the scanner.
* The scanner executes the provided policy and reports watchlist/focus outputs back to the orchestrator.
