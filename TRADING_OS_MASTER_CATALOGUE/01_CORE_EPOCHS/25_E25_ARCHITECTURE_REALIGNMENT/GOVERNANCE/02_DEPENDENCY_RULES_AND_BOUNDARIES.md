# Dependency Rules and Boundaries

## Layering (top to bottom)

1. **domain/** (pure)
2. **application/** (use cases, policies)
3. **engine/** (cycle orchestration, runners)
4. **adapters/** (IBKR, DB implementations, filesystem)
5. **cli/** and **gui/** (entrypoints)

## Allowed imports (directional)

- `domain` imports: standard library only (plus typing/dataclasses/pydantic if used), NO adapters.
- `application` may import: `domain`, `strategy`, `risk`, interfaces from `market_data/storage/execution`.
- `engine` may import: `application` + interfaces; may invoke adapters via factories.
- `adapters` may import core interfaces but must not be imported by core at module import time.
- `cli/gui` may import engine/application only.

## Rules

- **No adapter imports at module top-level** inside domain/application (lazy load via factories).
- **No DB file paths** embedded in core code; paths resolved from config and used in adapters.
- **No event loop policy manipulation at import boundary**. Only in `src/runtime/` bootstrap or entrypoints.
- Tests may install fixtures (event loop) but should not change production runtime policy.

## Runtime invariants (must hold)

- `python -c "import src"` must succeed without IBKR running, without DB present.
- `pytest -q` must pass on clean checkout with only Python deps installed.
