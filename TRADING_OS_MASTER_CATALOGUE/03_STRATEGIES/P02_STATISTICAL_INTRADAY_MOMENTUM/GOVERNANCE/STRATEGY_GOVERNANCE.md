# P02 — Statistical Intraday Momentum — STRATEGY GOVERNANCE
**Catalogue path:** `03_STRATEGIES/P02_STATISTICAL_INTRADAY_MOMENTUM/GOVERNANCE/STRATEGY_GOVERNANCE.md`  
**Timestamp:** 2026-02-08T00:52:50Z

## 1) Strategy boundaries (non-negotiable)
- This strategy is **continuation momentum**, not mean reversion.
- Stock selection is **eligibility + ranking**, not entry/trigger logic.
- Entries are executed only via canonical `XL_*` primitives.
- No strategy code may bypass OS risk engine, execution authority, or no-trade contexts.

## 2) Invariants
- **No partial coverage:** all canonical IDs are classified.
- **Traceability:** every decision produces an auditable artifact (E14/M4).
- **Mode parity:** strategy must behave consistently in SIM/PAPER/READ_ONLY/LIVE (E7).
- **Data provenance:** every feature has provenance (M10).

## 3) No-trade contexts (E16)
Strategy must not emit entry intents when:
- market closed or session phase disallowed
- stale/invalid reference prices
- spread/liquidity outside bounds
- max consecutive losses reached
- risk engine veto
- symbol cooldown active
- regime explicitly disallowed (if enabled)

## 4) Change control (M8)
Any parameter change must:
- occur only in `strategy_policy.py` knobs
- be accompanied by a verification run (E21)
- record a change note (what changed, why, expected impact)

## 5) Safety
- Default direction: LONG-only, unless explicitly certified for shorts.
- Event/halts: denied until specialised handling is certified.


## 2026-11-14 — DRAFT bounded native Template A bridge (not adopted or enabled)

This proposal is a new project calibration for a synthetic-only prerequisite,
not historical Ross doctrine and not a claim that the existing adapter is
complete. Root coordinator adoption after independent contract review is required
before implementing this proposal. The ordinary policy remains unchanged/off.

Existing authority: ALGORITHM execution law §0 requires conditions,
confirmations, a genuine SF, one XL and invalidation; Template A §10 permits
SF_OPENING_RANGE_BREAKOUT / 01_XL_ORB_BREAK / INV_LEVEL_LOSS. The existing P02
strategy_policy_v2.py T_OPENING_BREAK_HOLD requires a full structure-bar hold and
RVOL>=2. Its structural invalidation law uses level loss. Existing
strategy_policy.py supplies unchanged bar-score threshold .7, 30..360-minute
activation interval, .005..05 volatility band, liquidity/spread rules and explicit
2R numeric target construction. The proposed route must not substitute the
current adapter's gap/RVOL score for the native bar-based decision.

Proposed bounded definitions:

- Default off. A separate in-process TEST/PAPER/SMALL enrollment can exercise
  Template A only. The normal strategy enable flag does not imply enrollment;
  environment input, session overrides and SIM activation shortcuts cannot grant
  native admission. No additional strategy is enabled by default.
- Use the existing completed HistoricalDataResult, CandidateIdentity, session and
  reference owners. Require current-session, end-confirmed, security-bound STK/USD
  history with an identical positive con_id, finite valid OHLCV, aware timestamps,
  unique ordered contiguous one-minute bars and authoritative session boundaries.
  Unknown coverage, unresolved identity, gaps, stale/future/forming bars or missing
  required reference/quality facts block the route. No snapshot-to-bar fallback,
  internal level injection or renewal of old observations is permitted.
- NEW calibration proposal: measure the opening range from the first thirty
  completed one-minute bars after the actual RTH open. This aligns the native
  measurement with the existing P02 earliest activation minute30; it is not the
  Ross native ORB window. Aggregate five-minute structure bars only from complete
  blocks of that same one-minute stream aligned to the actual open.
- Require a whole completed five-minute structure bar, starting at or after range
  completion, whose low and close are strictly above measured OR high. Keep the
  canonical common SF detector and registered ORB trigger exercised with real
  measured inputs, plus the unchanged P02 native signal/regime/time thresholds.
  Equality, wick-only breakout, forming hold, missing source and weak bar score
  remain blocked. Retain V2 RVOL>=2 participation confirmation, all canonical C/K
  requirements, own occurrence identity and original quote/history provenance.
- NEW numeric mapping proposal: current executable long quote must be strictly
  above measured OR high; that level is the retained INV_LEVEL_LOSS structural
  stop. It is not the Ross OR-low stop. Keep the existing explicit P02 2R target
  authority, calculated from actual proposed quote entry and this structural stop
  through TakeProfitAuthority, subject to ordinary risk/target validation. Do not
  import Ross numeric-TP=None or invent a descriptive objective. This grants no
  trailing, reduction, adds, re-entry or recurring-management enrollment.
- Bar-score values are heuristic scores, not probabilities. Retain original
  features, weights and threshold. A finite raw score already in [0,1] may
  be carried as heuristic intent confidence; otherwise retain a veto, without
  clipping, constant uplift or gap/RVOL substitution to satisfy shared admission.
- Strategy output is a provisional proposal for the existing Core risk stage;
  C_RISK_ENGINE_APPROVED/K_RISK_ENGINE_GREEN_CONFIRM cannot be asserted until the
  actual shared risk decision. The admitted order remains contingent on all
  existing position-truth, recovery, daily-risk, ownership, inventory, capital,
  reservation and final-write guards. Unknown safety facts must veto admission.

Concrete implementation dependencies remain to be reviewed: the active adapter
has no native completed-context provider, policy activation is not wired to an
explicit native test opt-in, P02 V2 is not registered in the active V2 registry,
and active Core applies the Ross integrity triple to every strategy. The current
adapter genuinely lacks SF/XL/INV, so its PATTERN_INVALID rejection is a valid
contract veto, not evidence that removing that guard is safe. Existing E22/P9/
portfolio calls below the active manager return are unreachable; a positive
integration proof must use those existing owners in the active call graph, never
copy or activate the legacy tail. This draft neither removes a veto nor claims a
positive Core fill/accounting proof.

### Required C/K evidence map and exact unresolved prerequisites

This table is a proposed ownership map, not a declaration that the producer is
implemented or its UNKNOWN facts passed. Every listed required condition must
receive a bound, inspectable source fact; absence/conflict means veto.

| Canonical requirement | Existing evidence / owner and remaining dependency |
| --- | --- |
| C_TIME_OF_DAY_ALLOWED, C_SESSION_PHASE_ALLOWED | P02 ActivationSpec 30..360 minutes plus actual covered RTH boundaries. session_pct_change.covered_opening_window validates finite provenance/configuration but deliberately rejects post-minute30; extract a general covered-RTH primitive from its validator while preserving the existing opening-only wrapper. Do not call the opening validator with a forged earlier assessment time. |
| C_HALT_STATE_ALLOWED, C_SSR_STATE_ALLOWED | CandidateMetrics halted/ssr with known boolean source facts; stock_selection_spec.allow_halts=False / allow_ssr=True. Unknown halt/SSR provenance cannot become false by default; no halt-resumption enrollment. |
| C_DATA_QUALITY_OK, K_DATA_QUALITY_CONFIRM | Existing candidate quality/resolution flags, completed HistoricalDataResult, matching qualified CandidateIdentity and real quote snapshot. No cached positive flags or externally supplied detected setup. |
| C_REFERENCE_PRICE_VALID | Existing reference_resolved, reference_quality_tier and prior-completed-session reference provenance, bound to the same security; missing/nonpositive/nonfinite reference vetoes. |
| C_HAS_BID_ASK, C_SPREAD_WITHIN_LIMIT, K_SPREAD_CONFIRM | Original complete MarketSnapshot positive bid<=ask, quote_time_rejection and historical rejection flags; unchanged P02 25bps maximum, not the looser V2 narrative .60% threshold. Revalidate at proposal/risk/dispatch without replacing quote time by receipt time. |
| C_LIQUIDITY_WITHIN_MIN, K_LIQUIDITY_CONFIRM | P02 UniverseSpec minimum dollar volume20M, source-bound day volume and price; V1/V2 disagreement does not lower this threshold. |
| C_STALE_DATA_REJECT | Existing quote_time_rejection LAST_TRADE age limit and historical veto retention; newest fully completed 1m bar must belong to the current expected one-minute completion interval (proposed NEW interval-completeness calibration), with no gaps/future bars. Exact observation/assessment times stay distinct. |
| C_FLOAT_KNOWN_OR_ALLOWED | Existing statistical_stock_selection_spec float_max_millions200; proposed enrollment requires known finite positive float within that maximum, rather than treating unknown as permission. |
| C_LEVELS_BUILT_OK, C_INVALIDATION_DEFINED, C_SETUP_FAMILY_ACTIVE, K_INVALIDATION_PRESENT_CONFIRM | Security/session-bound measured OR from complete history; common SF detector; own Template A occurrence; independently retained stop/invalidation below executable proposed entry. No Ross detector policy or assumed OR-low anchor. |
| C_VOLATILITY_STATE_ALLOWED | Native P02 evaluate_regime / realized-return standard deviation .005..05; preserved independently of ATR. |
| C_ATR_WITHIN_BOUNDS | **UNRESOLVED POLICY.** ALGORITHM §4 and CAPABILITY_MAP require this condition, but no P02 ATR definition, lookback, unit, numerical lower/upper bounds or evaluator is present. The V1 return-stdev band is not ATR; risk_policy StopModelSpec atr_multiple1.5 is a placeholder stop multiplier, not admission bounds. This condition remains UNKNOWN and blocks native admission. |
| C_RELATIVE_VOLUME_OK, K_RELATIVE_VOLUME_CONFIRM | Existing source/resolution provenance for candidate RVOL plus P02 T_OPENING_BREAK_HOLD RVOL>=2. Missing usable execution RVOL does not pass. |
| C_ABSOLUTE_VOLUME_OK, K_VOLUME_CONFIRM | Existing statistical_stock_selection_spec min_volume500000 plus same-stream completed volume, independent of dollar-volume and bar-score evidence. |
| C_RISK_ENGINE_APPROVED, K_RISK_ENGINE_GREEN_CONFIRM | Actual shared RiskEngine, position truth, recovery/daily-risk/capital/reservation/final-write owners. NEW staged proposal/admission split requires explicit adoption; never mark this true before the risk decision or use a test ALLOW substitute. |
| C_STRATEGY_PERMISSION_OK | Existing strategy enable flag plus separate explicit default-off native test enrollment; no flag implies another. |
| C_MAX_CONSECUTIVE_LOSSES_NOT_REACHED | Actual DailyRiskGovernor source facts and configured limits; V2 separate two-/three-loss behavior is not implemented by enabling the adapter and cannot be called certified. Unknown durable accounting/loss facts veto; reuse the concurrent committed-accounting prerequisite. |
| C_SYMBOL_COOLDOWN_EXPIRED | ActivationSpec120-second cooldown needs a bound authoritative prior-entry/fill-history read through existing lifecycle/storage owners. Current P02 adapter does not implement it. A current-run empty result is not proof that prior-run durable history is empty. Missing/conflicting history must veto; no new parallel cooldown ledger. |
| C_NO_TRADE_CONTEXT_FALSE | Existing stop/breaker, daily-risk/recovery, position truth, portfolio and risk no-trade decisions; missing or uncertain authority remains blocking. |
| K_BREAK_AND_HOLD_CONFIRM (Template A) | Proposed whole completed 5m hold plus real registered ORB evaluator, with retained source/occurrence identity and one permitted XL; optional retest is outside this initial bridge. |

Exact next policy decision: define P02 ATR measurement (true-range/ATR formula,
completed timeframe and lookback), units and finite admissible bounds, with
source/evidence rationale independent of the desired positive fixture. This is
not another permission to flip activation and cannot be resolved by renaming the
existing return-volatility gate. Calendar/context/cooldown read guarantees and
complete C/K mapping must also be implemented and reviewed before admission.
Until then this document remains DRAFT/not adopted; native P02 PAPER admission
and a claimed positive Core accounting proof remain blocked.

V2 mandatory partials, stop migration and time-stop laws are not waived or
superseded by a possible future entry/fill/initial-protection proof. Such a bounded
proof would terminate before claiming managed continuation, full P02 deployment
or operational enrollment. Existing one-share/default behavior, all five ownership
vetoes and PAPER_READY=NO; PAPER_READINESS_GATE=FAIL remain.
