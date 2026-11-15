# P03 — Mean Reversion — STRATEGY GOVERNANCE
**Catalogue path:** `03_STRATEGIES/P03_MEAN_REVERSION/GOVERNANCE/STRATEGY_GOVERNANCE.md`  
**Timestamp:** 2026-02-08T01:01:41Z

## 1) Boundary
- P03 is mean reversion. It must not include momentum continuation entries.
- OPENING mode is stricter by default (optionally disabled) due to trend risk.

## 2) Invariants
- NO PARTIALS coverage across canon registries
- Policy is the single tuning surface (all thresholds in policy)
- Traceability + decision artifacts for every cycle
- Mode parity across SIM/PAPER/READ_ONLY/LIVE

## 3) Safety / No-trade contexts (E16)
- Strong-trend regime disallowed unless explicitly permitted
- Data quality failures block all intents
- Spread/liquidity limits enforced
- Loss-streak and cooldown enforced
- Halt handling denied unless certified

## 4) Change control (M8)
All changes must be parameter edits in strategy_policy + verification + certification note.


## 2026-11-15 — Bounded veto/source-fact reconciliation

This repairs the active legacy P03 policy/adapter/runner against the existing
immutable eight-clause contract and canonical ALGORITHM §4/§5. A veto produces
no proposal in every mode; SIM/PAPER do not supply a fallback trade.

Canonical required bid/ask, spread, data-quality, session/time and halt-state
conditions override the older local ScannerFacts prose describing spread/time
as optional. The active policy retains its existing configurable spread and
minute limits; this change does not adopt V2's different numerical calibration.
Both sides of the same quote must be finite, positive and non-crossed; its
spread is measured from ask minus bid and that measured spread controls the
existing cap. A supplied redundant spread may differ only by the sum of the
bid/ask machine ULPs (binary representation error, no trading tolerance).
A provided bad or incomplete snapshot cannot borrow another quote's fields.

The following explicit source-admission choices are NEW bounded project
reconciliation, not claims of historical strategy doctrine:

- Unknown/malformed configured halt/news veto facts and required index/macro
  permission facts remain unknown and refuse proposals. An aggregate regime
  label alone proves neither four individual index directions nor absence of
  a macro event. No current runner producer supplies those observations; its
  missing regime is a remaining blocker, not an all-False calm regime.
- The existing shared quote-time owner checks original LAST_TRADE timestamps,
  historical rejection flags and its unchanged configured maximum age, at the
  supplied aware assessment time. Missing, stale, future and unknown-time facts
  refuse. Acquisition time cannot replace market time; a current snapshot
  cannot erase retained selection quote rejections. Explicit candidate
  data_quality_ok=True and absence of candidate/snapshot quality errors are
  necessary, and cannot override missing quote-time evidence.
- Actual existing session resolution owns RTH_OPEN/MID/LATE and minutes since
  its 09:30 New York open. Coarse RTH/REG/REGULAR aliases constrain actual RTH;
  explicit phases must match. Missing/unknown/conflicting labels, naive or
  malformed assessment time, holidays/weekends/closed time and configured or
  environment overrides cannot grant eligibility. No new calendar is added.
- SSR remains optional selection metadata per V2 data_requirements and the
  scanner's allow_ssr=True. Missing SSR stays None, supplied booleans are
  retained, and malformed values refuse rather than becoming False. Neither
  known SSR status nor a policy SHORT proposal grants locate/borrow, short
  execution or Core admission. No new SSR execution rule is adopted.
- Optional absent exhaustion markers provide no supporting evidence. A string
  or integer cannot serve as a positive flag. Nonfinite/unrepresentable
  numerical inputs refuse rather than bypassing comparisons.

This is not complete P03 canon/certification, a positive Core execution proof,
short enablement or a production regime producer. Existing structural/risk,
ownership, lifecycle, default activation and management requirements remain.
No Ross/P02 management contract is imported. PAPER_READY=NO;
PAPER_READINESS_GATE=FAIL.

## 2026-11-15 — Source-producing regime prerequisite remains open

The completed PR1233 repair is not a source producer. The bounded offline
inspection/proposal in existing source-local governance
`src/strategies/mean_reversion/governance/07_REGIME_FILTERS.md` identifies exact
missing inputs: P03-specific index strong-trend measurement/calibration;
qualified, completed current-session SPY/QQQ source facts; and an approved
scheduled-release source/class/window/revision-completeness contract plus a
finite original offline receipt. No existing aggregate regime label, exchange
calendar, empty news response or illustrative False establishes this authority.

The proposed immutable handoff/revalidation shape is DRAFT and not adopted as
a complete contract while these decisions and actual inputs are absent. No
UNKNOWN-only carrier, source adapter, Core wiring or policy numerical change
is implemented. Preserve all required unknown-state vetoes and proceed with
independent ready work. This records a concrete dependency, not completion,
positive Core admission, natural validation or operational readiness.
PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.
