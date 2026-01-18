# PHASE INDEX — Track A (Ross Momentum)

Execute these phases in order.

- **A0** — Repo wiring audit & invariants freeze
- **A1** — Strategy integration contract (policy/context/runner interfaces)
- **A2** — Market session & timezone authority (NY session, UK display)
- **A3** — Signal pipeline alignment (scanner → signals → Ross policy inputs)
- **A4** — Entry engine (Gap & Go + first pullback + micro pullback) with deterministic intent creation
- **A5** — Exit engine mapping to Ross behaviours (partials, trailing, time/failure exits)
- **A6** — Per-symbol trade loop & re-entry controls + trade permission matrix enforcement
- **A7** — Risk overlay & kill conditions (daily loss, halts, topping-tail pause)
- **A8** — Paper trading harness (IBKR paper) + operator telemetry
- **A9** — Live readiness gate (preflight + checklist + hard arming)
- **A10** — Live trading rollout (gradual scale) + manual verification procedure
