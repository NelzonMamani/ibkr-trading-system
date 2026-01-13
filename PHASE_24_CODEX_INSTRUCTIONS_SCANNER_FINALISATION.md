# PHASE 24 — Codex Instruction Block (Scanner Finalisation: Cache‑First + News Fork + Field Contract Trim)

**Filename:** `PHASE_24_CODEX_INSTRUCTIONS_SCANNER_FINALISATION.md`  
**Status:** Authoritative single-block instructions for Phase 24 implementation.

---

## 0) Mission (What “done” means)

Implement Phase 24 by upgrading the scanner to be:

1. **Fast by design** (decision-first, enrichment-last; incremental; cache-first)
2. **Deterministic** (stable ranking/tie-breakers; repeatable outputs given same inputs/cache)
3. **Explainable** (explicit drop reasons; data-quality flags)
4. **Ross-compatible** (watchlist remains Ross-aligned)
5. **Fork-capable** (news evaluation supports Ross mode AND GAM‑EA mode without mixing strategy logic into the scanner)
6. **Field-contract compliant** (trim the current 54-field print into a decision-critical hot-path set; print links only for top 3–5)

Phase 24 is complete when:
- The scanner produces the watchlist reliably each cycle, with reduced hot-path fields.
- News processing is staged and forked (Ross vs GAM‑EA).
- Float is fetched once per day (premarket bootstrap) and then reused.
- Links are printed only for the final focus symbols (top 3–5).
- Drop reasons are recorded for symbols that fail gates.
- The system passes the Acceptance Tests in Section 8.

---

## 1) Inputs (You must read these artifacts first)

Codex MUST read and follow these Phase 24 blueprint documents (authoritative):
- `PHASE_24_SCANNER_BLUEPRINT_GAM_EA.md`
- `PHASE_24_GAM_EA_STRATEGY_SPEC.md`

These were delivered in the zip:
`PHASE_24_SCANNER_AND_GAM_EA_DOCS.zip`

Codex MUST treat the scanner blueprint as the source of truth for Phase 24.  
Codex MUST NOT invent new requirements outside those documents.

---

## 2) Scope Boundaries (Hard constraints)

### In scope
- Scanner: pipeline speed + determinism + explainability
- Float caching strategy (once/day)
- History caching (avg volume baseline, prior close) once/session
- News engine staging + forked evaluation outputs
- Print contract reduction and link-print rule
- Drop reason ledger and data quality flags

### Out of scope (DO NOT do these in Phase 24)
- Strategy execution logic (buy/sell)
- Risk engine redesign
- Patterns engine implementation
- Storage schema changes beyond adding new fields if needed for scanner output
- Large architectural refactors unrelated to scanner pipeline

If any codebase refactor is necessary for cleanliness, keep it minimal and limited to scanner modules.

---

## 3) Deliverables (What must be produced/changed)

### A) Scanner hot-path field contract
- Reduce the “54 fields” hot-path to a decision-critical set (see Section 6).
- Preserve explainability via rationale fields and drop reasons.
- Keep compatibility with downstream modules by returning structured outputs (dataclass / dict) with stable keys.

### B) News evaluation fork
- Implement news outputs supporting BOTH:
  - **Ross mode** (legitimacy/catalyst validation for discretionary confirmation)
  - **GAM‑EA mode** (early attention acceleration; news age ≤ 6h; velocity 5m/10m/30m; dilution kill-switch)
- Do not implement trading logic. Only emit structured “news context” to be used later.

### C) Cache-first scanning
- Float fetched once/day and cached (per symbol).
- History baseline cached once/session (avg vol baseline, prior close).
- News cache: dedupe headlines; do not repeatedly parse the same headlines each cycle.

### D) Output rules
- Print top-level cycle summary.
- Print per-symbol blocks for the watchlist (K symbols).
- Print links ONLY for final focus list (top 3–5).

---

## 4) Implementation Plan (Step-by-step)

### Step 4.1 — Locate/Confirm current scanner entrypoint
1. Identify the current scanner runner entrypoint(s) used by the orchestrator and standalone runs.
2. Confirm the current “54 field” output is produced somewhere (printer / formatter / print contract file).
3. Identify where float/news/history are fetched today and what is repeated per symbol/per cycle.

### Step 4.2 — Introduce explicit staged pipeline
Refactor (minimally) to enforce these stages:

**Stage 0: Bootstrap (premarket / once per day)**
- Load float cache from disk (if exists).
- For the initial candidate set (Top N), ensure float is fetched if missing.
- Persist float cache to disk.

**Stage 1: Market Lens (per cycle, Tier 0)**
- Pull Top N US % gainers from IBKR.
- Collect only L1 data needed for gating (price, pct change, volume, bid/ask/spread).

**Stage 2: Hard Tradability Gates (per cycle, Tier 1 + cached Tier 2)**
Apply gates in order; early exit and record drop reason:
- Price range
- % change / gap threshold
- Liquidity (volume, dollar volume, spread)
- RVOL threshold
- Float threshold (from cache; if missing -> data flag and deprioritise or drop per config)

**Stage 3: Watchlist build**
- Rank survivors by deterministic composite (or lexicographic) with stable tie-breakers.
- Select top K (default 10–15; config to 30).

**Stage 4: Deferred enrichment (watchlist only)**
- History (if not cached): prior close, avg vol baseline, key levels as needed.
- News discovery + validation (forked outputs).

**Stage 5: Print + return**
- Print reduced hot-path fields for K symbols.
- Print links only for top 3–5 focus list.
- Return structured data for downstream modules.

### Step 4.3 — Add drop ledger + data quality flags
- Create `DropReason` enum (or string constants) such as:
  - DROP_PRICE, DROP_GAP, DROP_RVOL, DROP_FLOAT, DROP_SPREAD, DROP_LIQUIDITY, DROP_NEWS_AGE, DROP_DILUTION
- Each dropped symbol gets ONE primary reason; optional secondaries.
- Add `data_quality_flags` list for:
  - FLOAT_UNKNOWN, HISTORY_UNKNOWN, NEWS_DELAYED, DATA_STALE

### Step 4.4 — Implement news fork (Ross + GAM‑EA)
Implement a unified `NewsContext` object with sub-views:

**Common fields (always)**
- `news_present: bool`
- `first_seen_ts`
- `top_domains` (top 1–2 by authority)
- `dilution_flag: bool`
- `catalyst_type: enum/string`
- `headlines_seen_count_windowed` (only if cheap; else keep minimal)

**Ross view**
- `ross_catalyst_valid: bool`
- `ross_catalyst_notes: str` (short)
- `ross_catalyst_category`

**GAM‑EA view**
- `news_age_minutes`
- `freshness_bucket` (0–30, 30–90, 90–180, 180–360)
- `velocity_5m`, `velocity_10m`, `velocity_30m`
- `attention_tier` (T0–T3) derived deterministically
- HARD RULE: if `news_age_minutes > 360` then mark `gam_ea_eligible = False`

**Important**
- Do not do NLP sentiment or keyword scoring in Phase 24.
- Do not compute region counts in Phase 24.
- If Google scraping is not implemented yet, create a provider interface stub (`NewsDiscoveryProvider`) and implement “verified RSS” as Provider A now; Provider B (Google) can be added in Phase 24 only if it is low-risk and reliable.

### Step 4.5 — Trim the “54 fields” hot-path
Implement two print profiles:
- `FAST_VIEW` (always printed for K watchlist)
- `DEEP_VIEW` (printed only for top 3–5 focus list)

Do NOT delete existing fields immediately; instead:
- keep them in structured returns if already present
- stop computing them in hot path
- mark as deprecated in comments

### Step 4.6 — Ensure determinism
- Sorting must use stable tie-breakers:
  1) primary metric(s)
  2) secondary metric(s)
  3) symbol string ascending
- Time windows must use consistent clock source (single “cycle timestamp”).

### Step 4.7 — Configuration
Add or confirm config values for:
- N (top gainers): default 50, max 100
- K (watchlist): default 10–15, max 30
- focus list: default 3–5
- thresholds: price min/max, gap/%change, RVOL, volume, dollar volume, spread max, float max
- GAM‑EA: news_age_max_minutes=360

---

## 5) Files to touch (Guidance)
Codex: identify actual repo paths. Likely areas:
- `src/scanner/` (runner, print contract, scoring/ranking)
- `src/data/` (float/history providers and caching utilities)
- `src/news/` (providers, dedupe, normalization)
- `src/core/` (orchestrator integration if required)

Do not restructure folders broadly unless necessary for clarity.

---

## 6) Phase 24 Field Contract (Required outputs)

### FAST_VIEW (watchlist K symbols)
Must include at minimum:
- symbol
- session (PRE/REGULAR/AFTER)
- last_price
- pct_change (or gap metric)
- volume
- dollar_volume
- bid, ask, spread, spread_pct
- rvol
- float (or FLOAT_UNKNOWN flag)
- scanner_rank
- scanner_score (simple; can be composite or explained)
- drop_reason (only if dropped from prior state; else empty)
- data_quality_flags
- news_present
- catalyst_type
- dilution_flag
- news_age_minutes (if available)
- velocity_5m/10m/30m (if computed)
- attention_tier (if computed)

### DEEP_VIEW (focus 3–5 only)
Additionally print:
- top 3–5 unique links (unique domains preferred)
- short catalyst rationale (1–2 lines)
- “why in focus list” explanation (1–2 lines)

---

## 7) Logging / Teaching requirements
- Logs must be teacher-style but short.
- Every cycle prints a summary: counts, elapsed time, data health.
- Every drop reason is logged when it occurs.
- Avoid spam: only print deep details for focus symbols.

---

## 8) Acceptance Tests (Must pass)

### Test A — Speed/Work Avoidance
- Verify float fetch happens once/day per symbol (cache hit on subsequent cycles).
- Verify history baseline fetch happens once/session per symbol.
- Verify news parsing is not repeated for unchanged headlines.

### Test B — Deterministic ranking
- Running two cycles with identical inputs produces identical ordering and scores.

### Test C — Correct output shaping
- Watchlist prints FAST_VIEW for K symbols.
- Focus list prints DEEP_VIEW and includes links.
- Removed fields are not computed in hot path.

### Test D — GAM‑EA gate correctness
- Symbols with news_age_minutes > 360 are marked ineligible in GAM‑EA view.
- Dilution flag always triggers exclusion in GAM‑EA view.

### Test E — Graceful degradation
- If float or news missing, scanner does not crash; sets data_quality_flags and continues.

---

## 9) Definition of Done (Phase 24)
Phase 24 is done when:
- All steps in Sections 4–8 are implemented and validated.
- Scanner matches the blueprint, produces stable output, and runs fast in realistic conditions.
- No regressions introduced in orchestrator integration.
- Code is clean, commented, and consistent with teaching-first standards.

---

## 10) Output Required From Codex
When Codex finishes, it must provide:
1. A concise summary of changes.
2. A list of files changed.
3. Evidence that Acceptance Tests were run (command + excerpt of logs).
4. Any TODOs deferred to Phase 25+ (Google discovery provider if not implemented).

END_OF_PHASE_24_INSTRUCTIONS
