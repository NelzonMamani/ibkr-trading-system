# IBKR Connection Ownership Audit

## Scope
Audited search targets across requested files:

- `client_id`
- `connect(`
- `disconnect(`
- `IbkrClient(`
- `IbkrBroker(`

Requested files:

- `src/adapters/brokers/ibkr/ibkr_client.py`
- `src/adapters/brokers/ibkr/ibkr_order_submitter.py`
- `src/brokers/ibkr_live_broker.py`
- `src/core_engine/orchestrator.py`
- `src/utils/capital_resolver.py`

## Findings Table

| file | line | function | action |
|---|---:|---|---|
| `src/adapters/brokers/ibkr/ibkr_client.py` | 54 | `IbkrClient.__init__` | assign id (`self.client_id = client_id`) |
| `src/adapters/brokers/ibkr/ibkr_client.py` | 90 | `IbkrClient.connect` | assign id (`base_client_id = int(self.client_id)`) |
| `src/adapters/brokers/ibkr/ibkr_client.py` | 92 | `IbkrClient.connect` | assign id (`client_id = base_client_id + attempt`) |
| `src/adapters/brokers/ibkr/ibkr_client.py` | 93 | `IbkrClient.connect` | assign id (`self.client_id = client_id`) |
| `src/adapters/brokers/ibkr/ibkr_client.py` | 98 | `IbkrClient.connect` | connect (`super().connect(...)`) |
| `src/adapters/brokers/ibkr/ibkr_client.py` | 114 | `IbkrClient.connect` | disconnect (`self.disconnect()`) |
| `src/adapters/brokers/ibkr/ibkr_client.py` | 134 | `IbkrClient.disconnect` | disconnect (`super().disconnect()`) |
| `src/adapters/brokers/ibkr/ibkr_client.py` | 145 | `IbkrClient.ensure_connection` | connect (`self.connect()`) |
| `src/adapters/brokers/ibkr/ibkr_order_submitter.py` | 54 | `OrderSubmissionSettings` | assign id (config field `client_id`) |
| `src/brokers/ibkr_live_broker.py` | 79 | `IbkrLiveBroker.__post_init__` | new IBKR client (`IbkrClient(...)`) |
| `src/brokers/ibkr_live_broker.py` | 82 | `IbkrLiveBroker.__post_init__` | assign id (`client_id=get_ibkr_client_id_order_submit()`) |
| `src/brokers/ibkr_live_broker.py` | 104 | `IbkrLiveBroker.__post_init__` | assign id (`OrderSubmissionSettings.client_id=...`) |
| `src/brokers/ibkr_live_broker.py` | 139 | `IbkrLiveBroker.ensure_connection` | connect (`self.client.connect()`) |
| `src/core_engine/orchestrator.py` | 81 | `_resolve_live_available_funds` | new broker (`IbkrBroker()`) |
| `src/core_engine/orchestrator.py` | 82 | `_resolve_live_available_funds` | connect (`broker.connect()`) |

No `disconnect()` call sites were found in `src/adapters/brokers/ibkr/ibkr_order_submitter.py`, `src/core_engine/orchestrator.py`, or `src/utils/capital_resolver.py`.

## Connection Authority Check

Expected canonical owner: `IbkrLiveBroker.ensure_connection()`.

Current status: **multiple authorities exist**.

Primary conflict observed in-scope:

- `src/core_engine/orchestrator.py::_resolve_live_available_funds()` instantiates `IbkrBroker()` and calls `broker.connect()`, which creates an independent connection path outside `IbkrLiveBroker.ensure_connection()`.

Additional repository-level conflict (discovered during global scan):

- `src/brokers/ibkr_broker.py` has its own connection lifecycle (`connect`, `disconnect`, `ensure_connection`) and constructs `IbkrClient` directly, which creates another connection authority.

## Determinism / client-id allocation impact

Because both `IbkrLiveBroker` and `IbkrBroker` can allocate and retry `client_id` independently, client-id ownership is not fully deterministic from a single authority.

## Recommendation

Unify all IBKR lifecycle entry points under `IbkrLiveBroker.ensure_connection()` (or an explicit shared connection manager used by it), and remove direct `IbkrBroker().connect()` use from orchestrator capital resolution paths.
