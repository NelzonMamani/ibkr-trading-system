# ibkr-trading-system

A modular, deterministic **trading operating system** designed to automate intraday trading strategies safely and explainably on **Interactive Brokers (IBKR)**.

The initial reference implementation is **Ross Cameron-style retail confirmation momentum**. The architecture is **strategy-agnostic**: additional strategies can be added as isolated plugins without redesigning the core.

---

## Governance model (authoritative hierarchy)

This repository is governed by a strict hierarchy. If any file conflicts with a higher-order file, the higher-order file controls:

1. **SYSTEM_CONSTITUTION.md** — immutable law (must not be edited except via explicit constitutional amendment)
2. **SYSTEM_STATE.md** — single source of truth for progress and what is enabled now
3. **Epoch governance** — e.g. `EPOCH_04_TRADE_LIFECYCLE_GOVERNANCE.md` (scoped authority for the current epoch)
4. **Frozen roadmap** — `SYSTEM_ROADMAP_EPOCH_02_TO_COMPLETION.md` (plan only; not a progress tracker)
5. Phase specifications — `PHASE_*.md` files (implementation contracts)
6. Code — must conform to the above, never the other way around

`README.md` is **descriptive** only and is not prescriptive.

---

## Current status (authoritative summary)

- Epoch 1 — Market Perception: **COMPLETE**
- Epoch 2 — Decision Intelligence: **COMPLETE**
- Epoch 3 — Risk & Execution: **COMPLETE** (safety-first gating; execution remains disabled by default)
- Epoch 4 — Trade Lifecycle & Persistence: **COMPLETE** (storage is authoritative for replay and reporting)

---

## Safety posture

- **Live market data** may be used in `LIVE_READ_ONLY` when configured and when IBKR/TWS is available.
- **Broker order routing is blocked by default.**
- **Execution is hard-disabled unless explicitly enabled and permitted by governance.**
- Replay is restricted in live modes by design.

---

## What Epoch 4 adds

Epoch 4 formalizes the **trade lifecycle record** as a persistable, replayable audit trail:

- Canonical **Trade Storage Schema**
- Deterministic **Replay** and **Timeline** reconstruction
- Performance and compliance reports derived from stored events/records
- Storage CLI and exports for audits and debugging

See:
- `EPOCH_04_TRADE_LIFECYCLE_GOVERNANCE.md`
- Phase docs: `PHASE_35_*` through `PHASE_38_*`

---

## Developer quick start

### 1) Create and activate a venv (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Run the system (teaching-first, safe defaults)
```powershell
python -m src.main
```

### 3) Run tests
```powershell
python -m pytest -q
```

---

## Repository notes

- The system is designed to be deterministic and explainable.
- The orchestrator is the “spine” of the runtime.
- Strategies must remain isolated and communicate via canonical contracts only.
