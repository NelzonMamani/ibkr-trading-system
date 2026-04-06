# Test Alignment Audit — Hierarchy Enforcement (PR #799)

## Why CONFIRM stage is no longer guaranteed

PR #799 introduced strict session-aware hierarchy-based setup selection. Under this behavior, the strategy pipeline may terminate earlier when a setup is disqualified at the pattern/risk gate. Because of this earlier termination point, execution does not always reach confirmation processing.

## Multi-stage blocking behavior

The current architecture allows valid blocking outcomes at multiple stages:

- `BLOCKED_AT_PATTERN`: blocking occurs immediately after pattern/trigger evaluation due to hierarchy/risk constraints.
- `CONFIRM_BLOCK` / `BLOCKED_AT_CONFIRMATION`: blocking occurs at the confirmation gate when earlier stages pass.

## Test update rationale

The affected test previously required confirmation-stage blocking logs only. That expectation is now too strict under hierarchy enforcement. The updated assertion accepts either confirmation-stage block evidence or pattern-stage block evidence, while still requiring no intents to be emitted (`decision.intents == []`).

This aligns test expectations with architectural intent without changing runtime logic.
