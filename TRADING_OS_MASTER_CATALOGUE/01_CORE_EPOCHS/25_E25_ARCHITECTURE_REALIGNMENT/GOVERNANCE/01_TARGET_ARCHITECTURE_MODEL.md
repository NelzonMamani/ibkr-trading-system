# Target Architecture Model

This is the target high-level tree (institutional grade). Not all folders must exist today; E25 defines where things *belong*.

```text
repo-root/
├── src/                          # Clean core (import-safe)
│   ├── domain/                   # Pure domain types, invariants, enums (no I/O)
│   ├── application/              # Use cases, orchestration, service layer
│   ├── engine/                   # Trading engine orchestration (cycles, scheduling)
│   ├── strategy/                 # Strategy interface + registry
│   ├── strategies/               # Strategy implementations (P01..P20)
│   ├── risk/                     # Risk rules, sizing, session limits
│   ├── execution/                # Execution logic (broker-agnostic)
│   ├── market_data/              # Market data interfaces (broker-agnostic)
│   ├── storage/                  # Storage interfaces + schemas (no concrete DB files)
│   ├── runtime/                  # Runtime bootstrap (event loop policy, process guards)
│   ├── adapters/                 # External system integrations (IBKR, filesystem, etc.)
│   │   ├── brokers/
│   │   ├── storage/
│   │   └── market_data/
│   ├── cli/                      # Thin CLI entrypoints calling application/engine
│   └── gui/                      # Optional UI entrypoints (if present)
│
├── tests/                        # Tests only
├── scripts/                      # One-off dev scripts (non-imported by core)
├── configs/                      # Default config templates (no secrets)
├── data/                         # Runtime data (DB files, baselines) — gitignored
├── output/                       # Generated outputs (watchlists, reports) — gitignored
├── logs/                         # Logs — gitignored
└── TRADING_OS_MASTER_CATALOGUE/  # Certification + governance catalogue
```

## Key principle

**`src/` must be import-safe**:
- Importing any module in `src/` must not require network, IBKR, DB file, or event loop side effects.
- External dependencies are allowed but must be **lazy** (runtime bootstrap) and isolated to adapters.

## UI approach

Institutional standard: UI is a separate *edge*.
- CLI/GUI should call **application services**, not embed business logic.
- If a GUI exists, it lives as `src/gui/` (thin) or separate top-level package (e.g., `ui/`).
- The *core* stays stable regardless of UI presence.

E25 does not force building a GUI; it only defines boundaries if/when one exists.
