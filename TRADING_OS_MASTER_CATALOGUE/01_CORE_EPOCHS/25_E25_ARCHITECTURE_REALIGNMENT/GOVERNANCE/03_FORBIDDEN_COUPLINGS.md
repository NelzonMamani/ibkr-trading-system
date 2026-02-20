# Forbidden Couplings (Hard Prohibitions)

Codex must treat these as **must-fix** if found.

## Forbidden

- `src/domain/*` importing:
  - `ib_insync`, `requests`, `sqlite3` (unless purely for typing and behind TYPE_CHECKING)
  - any `src.adapters.*`
  - filesystem paths to `data/` or `output/`

- `src/application/*` importing `src.adapters.*` directly.

- Any module in `src/*` (except `src/runtime/*` and entrypoints) calling:
  - `asyncio.get_event_loop()` or setting event loop policy at import time
  - network calls, socket calls, or broker connections at import time

- Tests depending on existing `data/*.db` committed artifacts.

## Allowed exceptions

- `src/runtime/*` may ensure event loop only when explicitly called.
- `src/adapters/*` may import `ib_insync` but should do so lazily behind runtime bootstrap.
