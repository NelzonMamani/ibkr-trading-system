# MODE BEHAVIOR MATRIX

The following matrix defines what each run mode MAY do and MUST NEVER do.

## SIM

MAY:
- Use simulated or mock data sources.
- Execute simulated order flows for testing.
- Run full strategy, risk, and lifecycle logic without broker submission.

MUST NEVER:
- Connect to live brokers for execution.
- Submit real orders.
- Depend on live account state.

## PAPER

MAY:
- Use live market data.
- Submit orders through paper execution providers only.
- Record paper fills for analytics.

MUST NEVER:
- Route orders to live brokers or live accounts.
- Bypass paper-only enforcement gates.

## READ_ONLY

MAY:
- Use live market data.
- Observe and log signals, intents, and risk decisions.
- Emit diagnostics and audit artifacts.

MUST NEVER:
- Submit, cancel, or modify orders.
- Enable execution paths that would reach broker submission.

## LIVE

MAY:
- Use live market data.
- Submit real orders when execution is explicitly enabled.
- Enforce risk, portfolio, and circuit-breaker constraints.

MUST NEVER:
- Submit orders when execution is disabled.
- Bypass safety gates (readonly flags, kill switches, execution enablement).

END
