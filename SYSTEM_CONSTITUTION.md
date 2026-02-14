# SYSTEM_CONSTITUTION.md
# SYSTEM CONSTITUTION (IMMUTABLE LAW)

## 0. Purpose
This document is the **immutable constitution** of the `ibkr-trading-system` repository.

It defines:
- The system’s **non‑negotiable safety guarantees**
- The **governance hierarchy** that controls all work
- The **epoch model** and strict boundary rules
- The **design invariants** required for correctness, explainability, and extensibility

If anything conflicts with this constitution, **the constitution wins**.

## 1. What this system is
`ibkr-trading-system` is a **modular, deterministic trading operating system** for intraday strategies, designed to be:
- **Explainable** (human-readable rationale at each decision step)
- **Governed** (explicit scope, permissions, and boundaries per epoch/phase)
- **Safe** (defense-in-depth controls on execution and capital risk)
- **Extensible** (new strategies can be added without rewriting core systems)
- **Auditable** (events, decisions, and outcomes are persistable and replayable)

The system integrates with **Interactive Brokers (IBKR)** as its primary data/execution venue, but the architecture supports additional brokers and data sources via adapters.

## 2. What this system is not
This system is **not**:
- A black-box “bot” that trades without traceability
- A high-frequency trading (HFT) engine
- A playground for ad-hoc experiments in production paths
- A system that can place real orders without explicit governance and safety gates

## 3. Governance hierarchy (order of authority)
When in doubt, **higher-order documents override lower-order documents**.

1) `SYSTEM_CONSTITUTION.md` — immutable law (this file)  
2) `SYSTEM_ROADMAP_*.md` — frozen roadmap(s) (plan; must not be silently changed)  
3) `SYSTEM_STATE.md` — the single source of truth for current progress  
4) `EPOCH_XX_*_GOVERNANCE.md` — scope & rules for the active epoch  
5) `PHASE_XX_*.md` — phase-level requirements and deliverables  
6) Code, tests, scripts, and docs — implementation details

### 3.1 README rule
`README.md` is **descriptive only** (public charter), never prescriptive.  
It must not introduce requirements that conflict with governance documents.

## 4. Epoch model and boundaries
Development proceeds in **epochs**. Each epoch has:
- A governance file defining permissions and prohibitions
- A sequence of phases with explicit deliverables
- A “definition of done” for the epoch

### 4.1 Canonical epoch progression
**Epoch 1 — Market Perception**
- Scanner, enrichment, caching, and canonical outputs
- Deterministic market observation with explicit drop reasons

**Epoch 2 — Decision Intelligence**
- Strategy contracts, pattern detection, explainability
- Produces *trade intent* (not orders)

**Epoch 3 — Risk & Execution**
- Risk gating, sizing, order translation, execution routing
- Hard safety controls and staged rollout (paper → sim → micro-live)

**Epoch 4 — Memory, Learning & Recovery**
- Storage schemas, post-trade review, replay, analytics feedback loops

**Epoch 5 — Scaling & Strategy Expansion**
- Strategy plug-in maturity, regime awareness, advanced strategy families

**Epoch 6+ — Long-horizon & Fundamentals (optional future)**
- Fundamental/portfolio cadence, different data pipelines
- Must remain isolated from intraday execution paths

### 4.2 Boundary rule
Each epoch **must not** implement functionality belonging to a later epoch unless:
- The later functionality is *strictly stubbed* (non-operational), AND
- The stub cannot enable real execution or capital risk, AND
- The stub is clearly labeled as “placeholder / disabled by design”.

## 5. Core system invariants (non-negotiable)
These invariants must remain true at all times.

### 5.1 Determinism and explainability
- All decisions must be reproducible given the same inputs.
- Every drop/reject decision must have explicit **reasons**.
- Strategies must emit explainable rationale and structured artifacts.

### 5.2 Strategy isolation
- Strategies must be isolated modules.
- No shared mutable state across strategies unless explicitly governed.
- Cross-strategy coupling is prohibited without explicit governance approval.

### 5.3 Decision → Risk → Execution separation
- **Scanner** observes and filters.
- **Decision intelligence** produces *intents* and rationales.
- **Risk** authorizes (or vetoes) intents and produces risk payloads.
- **Execution** translates authorized intents into orders and manages fills/exits.

No layer may bypass the next layer.
- Strategies cannot place orders.
- Risk cannot fetch market data as a side channel to override scanner contracts.
- Execution cannot invent intents.

### 5.4 Safety and guardrails (defense-in-depth)
The system must enforce safety via multiple redundant gates:
- Run modes (SIM / PAPER / READ_ONLY / LIVE)
- Execution enable flags (default off)
- Broker submission guards (block routing unless explicitly allowed)
- “Read-only” data mode that can never route orders

**Default posture:** safe-by-default; execution is off unless explicitly enabled.

### 5.5 Testability and regression safety
- Contracts must be backed by tests where feasible.
- Any change that affects outputs must be accompanied by:
  - Updated tests, or
  - Explicit acceptance criteria and audit logs

### 5.6 Event capture and audit trail
The system must be capable of persisting:
- Scanner outputs (candidates, watchlists, focus lists)
- Pattern evaluations and evidence tags
- Strategy decisions and intents
- Risk decisions
- Execution results (when enabled)
- Performance snapshots
- Run/cycle metadata and key configuration

## 6. Runtime modes (canonical meanings)
Run modes are constitutional concepts; their operational details are phase/governance defined.

- **SIM**: internal-only execution simulation; no broker routing
- **READ_ONLY**: live broker data allowed; *orders must be blocked*
- **LIVE**: live execution allowed only when execution is explicitly enabled and full risk controls pass. Micro/1-share constraints are risk profile settings, not run modes

Any ambiguity must resolve toward the **safer** interpretation.

## 7. Change control (how to evolve law without breaking it)
This constitution is immutable by default.

If a constitutional change is ever necessary, it must be handled as a **constitutional amendment**:
- Create a new file `SYSTEM_CONSTITUTION_AMENDMENT_YYYYMMDD.md`
- State the exact change, rationale, and impact
- Update `SYSTEM_STATE.md` to record that an amendment exists
- Do not silently edit this file in-place

## 8. Interaction rule for AI-assisted development
When using AI tools (e.g., Codex), the system must be protected from drift:
- The AI must be instructed to follow governance hierarchy.
- The AI must implement work **phase-by-phase**, within the epoch scope.
- The AI must not infer progress from code; it must read `SYSTEM_STATE.md`.

## 9. Security and operational hygiene (minimum standards)
- Secrets must never be committed.
- IBKR credentials, tokens, or private keys must not be stored in repo.
- Logs must avoid leaking sensitive account identifiers.
- Production-like execution must require explicit opt-in flags.

---

**End of SYSTEM_CONSTITUTION.md (immutable).**
