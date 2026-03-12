# AUDIT NOTE — IBKR Connection Manager Unification

## Previous defect summary
- Runtime had competing IBKR connection owners across capital resolution, live broker, and submit paths.
- Client-id retry happened in multiple layers, producing collisions and invalid retry state symptoms (`host=None port=None`).
- LIVE canonical capital could degrade due to secondary/competing connect paths.

## Runtime authorities removed/changed
- `src/core_engine/orchestrator.py` no longer instantiates `IbkrBroker()` for LIVE capital.
- `src/brokers/ibkr_live_broker.py` no longer owns direct `IbkrClient` construction/connection lifecycle.
- `src/brokers/ibkr_broker.py` converted to a manager-backed facade.
- `src/adapters/brokers/ibkr/ibkr_client.py` no longer performs internal client-id retry loops.

## Canonical owner after refactor
- `src/adapters/brokers/ibkr/ibkr_connection_manager.py::IbkrConnectionManager` is the sole runtime owner for:
  - `IbkrClient` construction
  - connect/reconnect attempts
  - deterministic client-id retries
  - connection metadata and disconnect

## Client-id allocation law
- One base client id source: `get_ibkr_client_id()`.
- One retry allocator: `IbkrConnectionManager` (base, base+1, ... deterministic).
- Connected client-id is recorded in manager metadata and logs.

## Shutdown law
- `ExecutionEngine.shutdown()` now calls broker `disconnect(reason="execution_engine_shutdown")` once.
- `IbkrLiveBroker.disconnect()` delegates to manager single disconnect.

## Before/after flow
- **Before**: Orchestrator capital path + live broker path + submitter path could each own/connect IBKR.
- **After**:
  1. Capital resolution requests manager client.
  2. Live broker requests same manager client.
  3. Submitter uses manager-provided client provider (no connect/disconnect ownership).
  4. Shutdown disconnects manager-owned session once.

## Proof/tests added
- `tests/test_ibkr_connection_manager_unification.py` covers:
  - single-owner client reuse
  - deterministic retry to next client-id
  - immutable host/port metadata during retry
  - orchestrator LIVE capital path manager usage
  - submitter does not connect/disconnect directly
  - shutdown disconnect once
- `tests/test_ibkr_connection_resilience.py` updated for manager config baseline.
