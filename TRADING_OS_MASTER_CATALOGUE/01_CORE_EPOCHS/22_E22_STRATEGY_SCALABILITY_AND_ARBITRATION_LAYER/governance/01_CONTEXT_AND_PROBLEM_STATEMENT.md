
# E22 Context and Problem Statement

The Trading OS is moving from a small number of strategies to a catalogue-scale target of **~20 strategies**. The current runtime must remain:

- Deterministic (repeatable, auditable)
- Safe (risk + permission gating holds)
- Efficient (bounded latency + bounded resource consumption)
- Maintainable (clear boundaries, minimal coupling)
- Verifiable (tests + evidence artifacts)

## The scaling problem
As strategy count increases, systems typically fail in predictable ways:

1) **Resource contention**
   - Market data subscriptions, snapshot requests, scanner calls, disk IO.
2) **Unbounded concurrency**
   - “async everywhere” without budgets leads to IBKR rate-limit failures and nondeterministic behaviour.
3) **Duplicate work**
   - Each strategy fetches the same market data, news, bars, float, etc.
4) **Conflicting intents**
   - Two strategies try to trade the same symbol or exceed portfolio/risk limits.
5) **No canonical prioritisation**
   - “whatever runs first wins” is not governance.
6) **Audit gaps**
   - System cannot explain why one strategy’s intent executed and another was suppressed.

E22 introduces a **Strategy Scalability & Arbitration Layer** that sits between:
- (A) strategy outputs (intents) and
- (B) execution/portfolio/risk engines

and also governs:
- strategy scheduling and resource budgets
- shared caches and request coalescing
- deterministic ordering and conflict resolution
- evidence generation for certification
