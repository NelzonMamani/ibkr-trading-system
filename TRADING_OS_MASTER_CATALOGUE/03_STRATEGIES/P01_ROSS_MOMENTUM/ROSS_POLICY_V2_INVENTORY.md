# ROSS_POLICY_V2_INVENTORY

Authoritative checklist for migrating P01 Ross Momentum policy into StrategyPolicyV2 (spec-only).

## 1) Strategy identity & purpose
- Strategy: `ROSS_MOMENTUM` / `P01`.
- Purpose: intraday U.S. equity momentum continuation strategy focused on in-play small/mid-cap runners with catalyst/attention.
- Time horizon: intraday only (open-drive emphasis; slower cadence midday/late day).
- Instruments in repo policy: U.S. stocks (`instrument=STK`, `location_code=STK.US.MAJOR`).

## 2) Modes: SIM/PAPER/READ_ONLY/LIVE semantics
- SIM: allowed; emits strategy decisions/intents for simulation flow.
- PAPER: allowed; same policy semantics as SIM.
- READ_ONLY: allowed to compute selection/ranking/pattern context, but no executable order intent.
- LIVE: documented but intentionally not wired in this migration (spec-only).

## 3) Session semantics: PRE/RTH/AH/OVN and market-closed behavior
- Session labels referenced in repo: PRE, REG/RTH, AFTER/AH, CLOSED (and generic mappings to mode).
- OPENING_DRIVE mode maps to premarket/opening phases.
- MIDDAY mode maps to midday/closed fallback in v1 mapping.
- LATE_DAY mode maps to late/power-hour phases.
- Market closed semantics: no new entries; policy remains evaluable for diagnostics/selection only.

## 4) Universe & selection plan
- Scanner-driven universe from IBKR top gainers.
  - `source=IBKR_TOP_GAINERS`
  - `ibkr_scan_code=TOP_PERC_GAIN`
  - `instrument=STK`
  - `location_code=STK.US.MAJOR`
- Selection sizing:
  - `top_n=50` baseline (`top_gainers_n=50`, premarket/closed session branch may use 150 in v1 helper).
  - `watchlist_k=15`
  - `focus_m=5`
- Ross “in-play” / tradability gates present in repo policy:
  - price range: min 1.0, max 20.0
  - gap min 10%
  - RVOL min 5
  - float max 20M
  - minimum volume 1,000,000 and premarket volume 100,000
  - catalyst required
  - halts not allowed for selection
  - SSR allowed
  - data quality requires price; bid/ask optional
  - gate check failures lead to candidate drop reasons
- Ranking authority:
  - Eligible symbols ranked by `(rank_score, pct_change, dollar_volume)` descending.
  - watchlist uses top `K`; focus uses top `M` downstream (trace artifacts show watchlist/focus split).
- Not present in repo; left out:
  - explicit news-source hierarchy/scoring model,
  - explicit spread max threshold value,
  - explicit halt-resume microstructure thresholds.

## 5) Setup families (Ross canonical setups; all found in repo)
- Gap & Go (opening drive)
- Opening Range Breakout (ORB)
- First Pullback / First Flag
- Micro Pullback
- Bull Flag / High-Tight Flag
- Break of Key Level (PMH, HOD, whole/half dollar, prior/multi-day)
- ABCD continuation / measured move
- Cup & Handle (intraday)
- Momentum Reclaim (VWAP/EMA reclaim)
- Red-to-Green / Green-to-Red contextual signal
- Premarket High Break
- Halt Resume Continuation
- Parabolic Exhaustion (avoid/exit family)

## 6) Candle pattern catalog (single + multi-candle)
- Single-candle evidence used in code/docs:
  - long upper wick / topping tail
  - marubozu
- Multi-candle evidence used in code/docs:
  - engulfing
  - three soldiers / three crows detector
  - micro pullback sequence (2-3 red candles)
  - tight consolidation/flag sequence
- Not present in repo; left out:
  - formal doji/hammer-only strategy rules,
  - quantified morning-star/evening-star entry framework.

## 7) Trigger/entry model (all entry types and time windows)
- Micro pullback trigger: first green candle breaks high of last red after 2-3 red pullback candles.
- First pullback continuation: reclaim pullback high / prior candle high break.
- Breakout trigger: break PMH/ORH/flag high/consolidation high with momentum.
- Reclaim trigger: reclaim VWAP/EMA9/EMA20 then continuation.
- Session/time windows in repo semantics:
  - OPENING_DRIVE (fast, 10s execution emphasis)
  - MIDDAY (reduced aggression)
  - LATE_DAY (slower structure, 1m execution, 5m structure)

## 8) Confirmations
- Volume expansion on breakout vs pullback volume contraction.
- MACD positive gate for entries; optional halt on MACD cross against.
- Hold-above structure confirmations: VWAP/EMA9/EMA20.
- In-play checks (gap/rvol/float/volume/catalyst/liquidity/data quality).
- Topping-risk safety: wick/body thresholds used for pause/halt.

## 9) Structure model (levels/zones)
- HOD/LOD
- Premarket high/low
- Opening range high/low
- VWAP
- EMA9 / EMA20
- Prior close and prior day levels
- Whole/half-dollar psychological levels
- Flag/pullback highs and lows
- Consolidation range boundaries

## 10) Risk model
- Explicit in v1 policy:
  - max consecutive losses = 3
  - no hard cap max trades per symbol by default (`None`)
  - no hard cap max reentries per symbol by default (`None`)
- Overlay (repo risk overlay module):
  - LONG-only
  - gap range filters
  - float ceiling
  - RVOL floor
  - confidence floor
  - symbol cooldown ticks
  - max attempts per symbol
- Gap/halt/slippage assumptions:
  - handled via gates + structure stops + pause/halt behavior; no explicit slippage constants found.
- Not present in repo; left out:
  - explicit per-trade risk amount in dollars,
  - explicit portfolio exposure cap formula.

## 11) Execution model
- Preferred order behavior: limit-style, structural triggers.
- Extended-hours consideration is allowed in strategy session semantics.
- Runtime routing constraints are not wired in V2 migration (spec-only).
- Not present in repo; left out:
  - broker-route selection matrix,
  - market-impact model by ADV bucket.

## 12) Position management
- Scale-ins/adds permitted only on valid continuation structure.
- Partials are part of Ross constitution/process.
- Averaging down is not supported as a rule.
- No fixed `max_adds` integer published in v1; left uncapped by strategy policy and controlled by risk/rules.

## 13) Trailing model
- Trail under pullback/flag low after continuation confirms.
- Tighten toward VWAP/EMA when momentum weakens.
- Topping warnings imply tighter protection and pause on new adds.
- Move toward break-even after partial realization where structure permits.

## 14) Exit model
- Structure stop (below pullback/flag/trigger level).
- Exit on VWAP/EMA loss shortly after entry attempt.
- Exit on failed breakout/reclaim failure.
- Halt/cool-off behavior on hard reversal/topping confirmation.
- Session/time exits: closed-session behavior blocks new entries; flattening handled by risk/runtime controls.

## 15) Failure modes / safety
- Missing required data -> pause/reject new entries.
- Spread/liquidity unacceptable -> reject candidate.
- Halted symbols disallowed by selection gate.
- SSR allowed but must be execution-feasible.
- Connection/data degradation -> diagnostics and no new executable intents.

## 16) Intent contract
- Intents/artifacts observed or required by policy modules:
  - `DECISION_INTENT`
  - strategy trade intent (`TradeIntent` flow)
  - scanner ranking intent: `ROSS_MOMENTUM_STOCK_SELECTION`
  - risk decision artifacts from overlay (`RiskDecision` / block events)
- Required metadata fields (spec-level): strategy ID/name, symbol, direction, entry model, stop model, optional target, rationale, risk flags, and selection ranking provenance.

## 18) Premarket Preparation Law
- Scan focus: gappers + top % gainers + RVOL + catalyst
- Map levels: PMH/PML, prior close, prior day levels, multi-day levels, whole/half dollars, VWAP/EMA9/EMA20, DAILY EMA200
- Room-to-run decision: ensure upside air to next major resistance; EMA200 treated as major boundary
- Output: “tradable today” decision context (spec-level; runtime wiring later)

## Reconciliation checklist vs v1
- Carried from v1 directly:
  - scanner universe and gates,
  - mode/timeframe semantics,
  - micro pullback mechanics,
  - topping risk thresholds,
  - indicator gates,
  - max consecutive losses,
  - session allowlist/ranking intent.
- Carried from Ross strategy docs/code in strategy folder:
  - expanded setup family list,
  - candle evidence catalog,
  - breakout/pullback/reclaim triggers,
  - position/trail/exit/safety semantics.
- Explicitly not found and therefore not invented:
  - fixed dollar risk-per-trade,
  - exact slippage model constants,
  - exact router/venue constraints,
  - strict numeric spread cap in v1 Ross policy.

## 19) Intrabar Execution Law (OPENING_DRIVE + MICRO_SCALP)
- Phase map (spec-law):
  - PREMARKET_PREP: DAILY/5M/1M analysis only; no trading intents.
  - OPENING_DRIVE: 5M+1M structure with 10SEC execution and intrabar trigger permission.
  - MORNING_MOMENTUM: still aggressive; 10SEC execution remains permitted.
  - MIDDAY: reduced aggression; 1M-first execution, 10SEC precision optional.
  - POWER_HOUR/LATE_DAY: timeframe compression (5M acts like morning 1M; 1M acts like morning 10SEC) with slower cadence.
  - AFTER_HOURS: conservative mode under session semantics with tighter safety constraints.
- Candle-close law:
  - OPENING_DRIVE Gap&Go/immediate momentum entries do not require 1M candle close.
  - 10SEC intrabar triggers are explicitly allowed in morning fast phases.
  - Slower phases prefer candle-close confirmation.
- Cadence and micro-scalp doctrine:
  - "Control buy / control close" rapid loops are allowed in OPENING_DRIVE/MORNING_MOMENTUM.
  - Repeated attempts are allowed only under risk overlay and max consecutive loss constraints.
  - Burst cadence doctrine: 15-60 minute morning burst on 1-3 primary names; automation may manage up to `focus_limit_m` with strict gating.
- Symbol rotation law:
  - Prioritize focus-list leaders; trade the best 1-3 names rather than everything.
  - Rotate when weakness, invalidation, or structure failure appears; reallocate to cleaner continuation names.
- Safety throttles (spec-only):
  - Spread/liquidity sanity and halt policy interactions can suspend micro-scalp loops.
  - Connection/latency degradation blocks rapid-fire intents.
  - Cancel/replace churn guard limits unstable rapid order management behavior.
- Setup-family relationship:
  - Gap&Go, ORB, First Pullback, Bull Flag, ABCD, Momentum Reclaim, and related continuation families may all execute through OPENING_DRIVE micro-scalp on 10SEC entries.
  - Micro pullback is explicitly an execution tool used especially in the morning; afternoon behavior is governed by compressed timeframes and slower cadence.

## 20) Stock Selection Structural Doctrine (5 Pillars Expanded)
- `StockSelectionLawV2` is explicitly formalized with six structural components:
  - `PriceModelV2`: min/max price band, preferred upper band, and sub-dollar rejection doctrine.
  - `GapModelV2`: hard and soft gap thresholds, plus explicit distinction between eligibility gap logic vs ranking percent-change logic.
  - `VolumeModelV2`: minimum total volume, minimum premarket volume, and minimum dollar volume with liquidity commentary.
  - `RelativeVolumeModelV2`: standalone RVOL floor and calibration commentary; RVOL remains separate from raw volume.
  - `FloatModelV2`: float ceiling, preferred/explosive zones, inverse ranking weighting, multi-source float doctrine (YAHOO/FINVIZ/NASDAQ), IBKR-secondary rationale, and cache commentary.
  - `CatalystModelV2`: catalyst-required structural law with quality levels, internal-news primary preference, RSS fast-list support, and liquidity-proxy fallback when catalyst certainty is imperfect.
- `LiquiditySanityModelV2` is formalized with spread cap, halt policy, SSR handling, and execution-feasibility doctrine.
- `RankingModelV2` is formalized with weighted factors (`pct_change`, `rvol`, inverse float, catalyst) and explicit liquidity penalty semantics.
- Calibration doctrine is made explicit where thresholds may evolve:
  - `calibration_notes="Subject to empirical validation; current values reflect documented Ross doctrine."`
- Float is structural (not optional) in required metadata fields.


## 21) Session Reference Law
- `SessionReferenceLawV2` is formalized as a spec-only policy surface; runtime wiring deferred.
- `% change` law:
  - reference = prior close
  - valid in PRE/AH/CLOSED because it does not require the active RTH opening print.
- `gap` law:
  - reference = open vs prior close
  - meaningful primarily around open/RTH transition; not the primary CLOSED-preparation ranking primitive.
- CLOSED prep doctrine:
  - pre-open prep uses `% change` ranking + catalyst/volume context;
  - avoid calling CLOSED prep lists "active gappers" until open-reference context exists.

## 22) Candle/Volume Evidence Law
- `CandleAndVolumeEvidenceModelV2` is formalized as spec-only; runtime wiring deferred.
- Evidence tags now explicitly include:
  - `DOJI`
  - `SHOOTING_STAR`
  - `HAMMER`
  - plus existing evidence tags (`LONG_UPPER_WICK`, `MARUBOZU`, `ENGULFING`, `THREE_SOLDIERS_CROWS`).
- Risk/exit/pause semantics:
  - DOJI = indecision warning / reduce aggression.
  - SHOOTING_STAR = rejection/topping warning / pause or exit bias.
  - HAMMER = reclaim potential only with follow-through confirmation.
- Volume-bar dominance doctrine:
  - Rising red volume during pullback/consolidation signals selling-pressure control.
  - Policy response is pause adds, tighten risk, and bail when breakout/reclaim thesis fails.

## 23) Trigger/Entry Taxonomy Expansion (mapped to Intrabar phases)
- Added trigger specs:
  - `T_GAP_AND_GO_IMMEDIATE` (OPENING_DRIVE): no 1M candle-close requirement; intrabar permitted.
  - `T_STARTER_POSITION_ANTICIPATION` (OPENING_DRIVE/MORNING_MOMENTUM): optional, spec-only, calibration dependent.
  - `T_BREAKOUT_OR_BAILOUT` (OPENING_DRIVE/MORNING_MOMENTUM/MIDDAY): failure-fast rejection doctrine.
  - `T_ORB_1M` and `T_ORB_5M`: explicit ORB variants, both mapped to OPENING_DRIVE execution law.
- Mapping law:
  - OPENING_DRIVE retains intrabar execution authority;
  - slower phases still prefer increased confirmation/candle-close discipline.

## 24) Float Tier Doctrine
- `FloatModelV2` tiers are made explicit in doctrinal text:
  - preferred low-float tier (roughly sub-10M) for momentum responsiveness.
  - ultra-low-float explosive tier (roughly sub-5M) with elevated halt/slippage risk.
- Float remains structural and sourced from multi-provider references with cache/source-attribution doctrine.

## 25) Confirmation Layer (MACD + volume-bar rules)
- MACD semantics in V2:
  - MACD is a confirmation feature with calibration notes, not universally forced as hard-required for every entry.
- Volume-bar confirmation semantics:
  - breakouts prefer expansion volume;
  - rising red dominance during pullback/consolidation is explicit pause/bail evidence.
- Data requirements alignment:
  - float and news catalyst remain structural required fields.
  - newly introduced session-reference evidence fields are optional with explicit fallback semantics.
