# 04_PAPER_EXECUTION_AND_VERIFICATION.md
TITLE: PAPER Trading Lifecycle + Deterministic Verification Architecture
DATE: 2026-01-31

## 1. Goal
Make PAPER a first-class execution path with the **same lifecycle** as LIVE, so the system can be proven tradable before enabling real orders.

## 2. Non-negotiables
- PAPER must not be a toy. It must simulate fills, commissions, and order states deterministically.
- PAPER and LIVE must consume the same `OrderIntent` contract and produce the same `ExecutionReport` contract.
- Verification must be automated and deterministic.

## 3. Deliverables (ordered)

### 3.a Execution provider abstraction
Introduce/ensure a clean interface:
- `ExecutionProvider.place_order(intent) -> ExecutionReport`
- `ExecutionProvider.cancel(order_id) -> CancelReport`
- `ExecutionProvider.get_positions() -> PositionSnapshot`
- `ExecutionProvider.get_open_orders() -> list[OrderSnapshot]`

Implementations:
- `IBKRExecutionProvider` (LIVE, LIVE_READ_ONLY)
- `PaperExecutionProvider` (PAPER)

LIVE_READ_ONLY must:
- connect to IBKR for data
- hard-block any `place_order` calls (return “blocked” reports)

### 3.b PaperExecutionProvider (deterministic)
PaperExecutionProvider must:
- accept intents
- simulate fills (market and limit at minimum)
- support partial fills (configurable)
- apply latency/slippage (configurable, seeded)
- apply commissions (configurable)
- emit consistent timestamps

### 3.c Position + trade state
PAPER must update the same internal state objects and DB tables as LIVE:
- positions
- fills
- orders
- executions
- risk events

No paper-only schema. Use `execution_mode` tags.

### 3.d Risk profile enforcement boundary
Enforce risk profiles at the boundary where strategy intents become executable orders:
- clamp shares (MICRO=1 share)
- block adds if allow_scaling=false
- enforce daily loss / trade caps
- enforce hard stops

**Risk logic must consume `src/config/risk_profiles.py`.**

### 3.e Deterministic verification harness
Add a deterministic harness that can run:
- CLOSED weekend prep scenario
- PRE scenario
- RTH scenario with synthetic candles/ticks

Outputs must be repeatable:
- same watchlist
- same intents
- same fills
- same DB records

### 3.f CLI / run commands (minimal)
System must support:
- `--mode PAPER`
- `--mode LIVE_READ_ONLY`
- `--mode LIVE`

If SIM remains, it must be dev-only and not part of readiness.

## 4. Acceptance tests (hard)
- In PAPER, an entry order results in:
  - an ExecutionReport
  - a DB order row
  - a DB fill row
  - a position row updated
- In MICRO profile, shares are clamped to 1 across entries and adds are blocked.
- LIVE_READ_ONLY cannot place orders under any circumstances.
- A single “verification command” produces PASS/FAIL for end-to-end lifecycle.

END
