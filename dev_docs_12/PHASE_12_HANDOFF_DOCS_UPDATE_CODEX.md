PHASE_12_HANDOFF_DOCS_UPDATE_CODEX.md

SCOPE
You are Codex operating on the `ibkr-trading-system` repository.
Your job is to make the project transferable to a new AI by writing canonical documentation.
Do NOT implement trading logic changes in this step.
Only documentation and (if missing) minimal “how to run tests” commands.

GOALS
1) Update README.md with a clear repo structure, safety rules, and run commands.
2) Add docs that explain architecture, roadmap, invariants, testing, and AI handoff.
3) Ensure a new AI can start work without reading prior chat history.

RULES
- Do not change orchestrator/strategy/execution behavior.
- Do not add live trading capability.
- Documentation must match current code and printed logs.
- Prefer explicit file paths and explicit commands.
- Include a “Definition of Done” checklist.

TASKS

1) UPDATE README.md
Add these sections:
- What this repo is (teaching-first IBKR trading system skeleton)
- Safety model (SIM-first, kill switches, never live by default)
- Quickstart (venv, install, run main loop)
- How to run single-order CLI submission (Phase 12 Step 12.5)
- Configuration overview (RUN_MODE, IBKR_* flags, event replay mode)
- Repo Structure (tree-style list of src modules)
- “Project Status” summary with current phase and what is implemented
- “Next Steps” pointing to docs/ROADMAP.md

2) CREATE docs/ARCHITECTURE.md
Include:
- High-level dataflow: Scanner -> Pattern -> Strategy -> Risk -> Execution -> Exit -> Storage
- Event model: EventCollector, replay modes, invariants
- Where broker integration lives and how it is guarded
- Current limitations (teaching placeholders, static candidates, deterministic sim)

3) CREATE docs/ROADMAP.md
Include:
- Phase list (Phase 4 teaching core; Phase 12 broker integration; Phase 13+ Ross momentum automation)
- Each phase must have steps with a checkbox format:
  - [ ] step name
  - Definition of Done
  - Key files involved
- Add a dedicated “Ross Momentum Automation” section:
  - Signals (micro pullback, bull flag, HOD/PMH breaks, ORB)
  - Setups builder
  - Risk model
  - Trade management
  - Backtest harness
  - Metrics/journaling

4) CREATE docs/RULES_ROSS_MOMENTUM.md
Write a distilled “system rulebook” structure (placeholders are OK if exact thresholds not yet coded):
- Universe filters
- Scan thresholds
- Signal definitions (with inputs/outputs)
- Setup definitions (entry/stop/targets)
- Risk rules (R-based sizing, max daily loss, max trades)
- Execution constraints (spread/liquidity/halts)
- Management rules (partials, BE stop, trailing)
Mark each item as:
- (IMPLEMENTED) or (NOT YET IMPLEMENTED) or (PLACEHOLDER)

5) CREATE docs/INVARIANTS.md
List non-negotiable safety invariants:
- Default RUN_MODE=SIM
- LIVE mode must be blocked unless explicit override exists (if not, state “LIVE unsupported”)
- IBKR_READONLY_ENABLED blocks any orders
- Kill-switch for max daily loss
- Single-order CLI cannot submit more than one order
- Orchestrator loop cannot route broker orders

6) CREATE docs/TESTING.md
Add:
- How to run unit tests (pytest)
- How to run main loop in SIM
- How to run event replay
- Add “golden replay” concept (even if fixtures not created yet, describe future plan)

7) CREATE docs/HANDOFF.md
This is the “New AI Start Here” document.
Include:
- What NOT to do (do not enable LIVE trading; do not bypass kill switches)
- How to understand system from logs (event types list)
- Where to implement Ross automation (signals/setups/risk)
- The exact next implementation milestones and acceptance criteria

DELIVERABLES
- README.md updated
- docs/ARCHITECTURE.md created
- docs/ROADMAP.md created
- docs/RULES_ROSS_MOMENTUM.md created
- docs/INVARIANTS.md created
- docs/TESTING.md created
- docs/HANDOFF.md created

OUTPUT FORMAT
After edits, print a brief summary:
- Files changed/created
- Bullet list of what a new AI should do next

END