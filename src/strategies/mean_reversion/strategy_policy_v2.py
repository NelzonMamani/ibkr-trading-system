"""
P03_MEAN_REVERSION — StrategyPolicyV2 (institutional, fully-specified)

Intent
- P03 targets statistical intraday mean-reversion from overextension/exhaustion back toward
  VWAP / prior close / opening range / HTF pivots.
- This is not a breakout continuation strategy. It is explicitly anti-extension and risk-controlled.

Design constraints
- Deterministic defaults (no hidden magic).
- Explicit optional vs required semantics.
- Compile-safe: only uses models defined in src.strategy_policy_v2.policy_v2.
"""

from __future__ import annotations

from src.strategy_policy_v2.policy_v2 import (
    # Core
    StrategyPolicyV2,
    StrategyIdentityV2,
    ModeSemanticsV2,
    SessionSemanticsV2,
    SessionReferenceLawV2,
    IntentContractV2,
    DataRequirementsV2,
    PremarketPreparationModelV2,
    PremarketLevelSpecV2,
    PremarketFilterSpecV2,
    # Selection / ranking / liquidity
    StockSelectionLawV2,
    PriceModelV2,
    GapModelV2,
    VolumeModelV2,
    RelativeVolumeModelV2,
    FloatModelV2,
    CatalystModelV2,
    LiquiditySanityModelV2,
    RankingModelV2,
    # Setups / patterns / triggers
    SetupFamiliesV2,
    SetupFamilySpecV2,
    PatternCatalogV2,
    PatternSpecV2,
    TriggerModelV2,
    TriggerEntrySpecV2,
    ConfirmationSpecV2,
    # Structure
    StructureModelV2,
    # Risk / execution / management
    RiskModelV2,
    ExecutionModelV2,
    PositionManagementV2,
    TrailingModelV2,
    TrailingRuleV2,
    ExitModelV2,
    ExitRuleV2,
    SafetyModelV2,
    SafetyRuleV2,
    StrategyDomainExtensionSurfaceV2,
    InitialStopModelV2,
    TargetHierarchyModelV2,
    # Intrabar execution
    IntrabarExecutionModelV2,
    IntrabarPhaseSpecV2,
    IntrabarTimeframeMapV2,
    IntrabarCadenceRuleV2,
    IntrabarSafetyThrottleV2,
    SymbolRotationLawV2,
)
from src.strategy_policy_v2.selection_plans import ScannerPlan


POLICY_V2 = StrategyPolicyV2(
    identity=StrategyIdentityV2(name="MEAN_REVERSION", strategy_id="P03"),

    # ----------------------------
    # Selection plan (scanner feed)
    # ----------------------------
    # Baseline from v1: IBKR_TOP_GAINERS / TOP_PERC_GAIN, top_n=75, watchlist_k=20, focus_m=5, REG-only.
    selection_plan=ScannerPlan(
        universe_source="IBKR_TOP_GAINERS",
        ibkr_scan_code="TOP_PERC_GAIN",
        top_n=75,
        watchlist_limit_k=20,
        focus_limit_m=5,
        policy_name="MEAN_REVERSION",
        gating_profile="MEAN_REVERSION",
        session_allowlist=("RTH",),
    ),

    # ----------------------------
    # Run-mode semantics
    # ----------------------------
    mode_semantics=ModeSemanticsV2(
        sim_notes="SIM runs full mean-reversion gates and emits complete decision artifacts for audit.",
        paper_notes="PAPER mirrors SIM behavior; emits broker-safe intents; no discretionary shortcuts.",
        read_only_notes="READ_ONLY evaluates selection/setup/risk but blocks executable intents.",
        live_notes="LIVE permitted only when runtime governance enables this strategy and portfolio envelope.",
    ),

    # ----------------------------
    # Session semantics + reference law
    # ----------------------------
    session_semantics=SessionSemanticsV2(
        sessions=("PRE", "RTH", "AH", "OVN", "CLOSED"),
        market_closed_semantics="CLOSED/OVN blocks new entries; only risk-reduction actions permitted.",
    ),
    session_reference_law=SessionReferenceLawV2(
        pct_change_reference="Percent-change references prior RTH close for cross-session continuity.",
        gap_reference="Gap references current RTH open versus prior close (context variable for gap-fill setups).",
        closed_session_preparation_notes="CLOSED/OVN are preparation-only; no execution intents are emitted.",
    ),

    # ----------------------------
    # Risk / execution envelope
    # ----------------------------
    risk_model=RiskModelV2(
        # Mean reversion is adverse-selection prone; be conservative.
        max_position_pct=0.05,
        daily_loss_limit=0.012,
        max_open_positions=4,
        notes=(
            "P03 is mean-reversion and must be conservative: smaller per-position cap, bounded concurrency, "
            "and fast failure recognition. Conviction sizing doctrine (within the fixed cap): "
            "Tier A (clean exhaustion + reclaim evidence) can use full policy size with at most 1 add; "
            "Tier B uses reduced size with no adds; Tier C is probe-only or no-trade depending on regime gate."
        ),
    ),
    execution_model=ExecutionModelV2(
        preferred_order_types=("LIMIT", "STOP_LIMIT"),
        allow_market_orders=False,
        allow_extended_hours=True,
        notes=(
            "Price-controlled execution. Mean reversion requires discipline: limit-first entries and explicit invalidation stops. "
            "Extended-hours participation allowed only when spread/liquidity gates are satisfied."
        ),
    ),
    intent_contract=IntentContractV2(
        emitted_intents=("DECISION_INTENT", "TRADE_INTENT", "RISK_DECISION"),
        emitted_artifacts=("strategy_decision", "setup_evaluation", "risk_snapshot", "exit_decision"),
        notes="Artifacts MUST include setup_family_id, trigger_id, and trace_id for audit traceability.",
    ),

    # ----------------------------
    # Setup families (P03-specific)
    # ----------------------------
    setup_families=SetupFamiliesV2(
        families=(
            SetupFamilySpecV2(
                "VWAP_SNAPBACK_REVERSION",
                "VWAP Snapback Reversion",
                "Overextension then reversion toward VWAP after exhaustion evidence and reclaim/acceptance.",
                ("15MIN", "5MIN", "1MIN", "10SEC"),
            ),
            SetupFamilySpecV2(
                "HOD_FADE_EXHAUSTION",
                "HOD Fade Exhaustion",
                "Failed continuation at/near HOD (or key HTF resistance) after climax/exhaustion; fade into mean.",
                ("15MIN", "5MIN", "1MIN", "10SEC"),
            ),
            SetupFamilySpecV2(
                "GAP_FILL_PULLBACK",
                "Gap-Fill Pullback",
                "Large gap-up/extension then rotation down to fill gap toward prior close / OR levels.",
                ("15MIN", "5MIN", "1MIN"),
            ),
            SetupFamilySpecV2(
                "OPENING_FLUSH_REVERSAL",
                "Opening Flush Reversal",
                "Sharp opening selloff flush into support then reclaim/hold to revert toward VWAP/OR midpoint.",
                ("5MIN", "1MIN", "10SEC"),
            ),
            SetupFamilySpecV2(
                "FAILED_RECLAIM_RISK_OFF",
                "Failed Reclaim Risk-Off",
                "Failure family used for exits/no-reentry after snapback attempt fails and trend resumes against position.",
                ("5MIN", "1MIN", "10SEC"),
            ),
        )
    ),

    # ----------------------------
    # Pattern catalogue
    # ----------------------------
    pattern_catalog=PatternCatalogV2(
        patterns=(
            PatternSpecV2(
                "PATTERN_VWAP_SNAPBACK",
                "VWAP Snapback",
                "MULTI_CANDLE",
                "Entry pattern for VWAP_SNAPBACK_REVERSION",
            ),
            PatternSpecV2(
                "PATTERN_HOD_FADE",
                "HOD Fade Exhaustion",
                "MULTI_CANDLE",
                "Entry pattern for HOD_FADE_EXHAUSTION",
            ),
            PatternSpecV2(
                "PATTERN_GAP_FILL_ROTATION",
                "Gap Fill Rotation",
                "MULTI_CANDLE",
                "Entry pattern for GAP_FILL_PULLBACK",
            ),
            PatternSpecV2(
                "PATTERN_OPENING_FLUSH",
                "Opening Flush Reversal",
                "MULTI_CANDLE",
                "Entry pattern for OPENING_FLUSH_REVERSAL",
            ),
            PatternSpecV2(
                "PATTERN_FAILED_RECLAIM",
                "Failed Reclaim Risk-Off",
                "RISK",
                "Exit/no-reentry pattern for FAILED_RECLAIM_RISK_OFF",
            ),
        )
    ),

    # ----------------------------
    # Triggers + confirmations
    # ----------------------------
    trigger_model=TriggerModelV2(
        entries=(
            TriggerEntrySpecV2(
                "T_VWAP_RECLAIM_ACCEPT",
                "MEAN_REVERSION_LONG",
                "After pullback from extension, reclaim VWAP and hold for >=2 1MIN bars with stable spread and no halt.",
                ("RTH",),
            ),
            TriggerEntrySpecV2(
                "T_HOD_FAIL_AND_BREAKDOWN",
                "MEAN_REVERSION_SHORT_OR_RISK_OFF",
                "HOD test fails with exhaustion evidence; break back below prior pivot/ORH then continuation stalls -> fade into mean.",
                ("RTH",),
            ),
            TriggerEntrySpecV2(
                "T_GAP_FILL_TO_PRIOR_CLOSE",
                "MEAN_REVERSION_SHORT",
                "Large gap/extension rotates down; accept below OR levels and target gap-fill toward prior close with controlled tape.",
                ("RTH",),
            ),
            TriggerEntrySpecV2(
                "T_OPENING_FLUSH_RECLAIM",
                "MEAN_REVERSION_LONG",
                "Opening flush to support then reclaim ORL/level with improving spread and participation stabilization.",
                ("RTH",),
            ),
            TriggerEntrySpecV2(
                "T_FAILED_RECLAIM_EXIT",
                "RISK_OFF",
                "Snapback attempt fails (VWAP/level reclaimed then lost) with rising opposing participation -> force de-risk/exit.",
                ("RTH",),
            ),
        ),
        confirmations=(
            # Core operational
            ConfirmationSpecV2("C_DATA_FRESHNESS", "Required fields are present and fresh at decision time."),
            ConfirmationSpecV2("C_LIQUIDITY_SPREAD", "Liquidity passes minima and spread_pct <= configured spread max."),
            ConfirmationSpecV2("C_STRUCTURE_ANCHOR_PRESENT", "A clear mean anchor exists (VWAP / prior close / OR levels / HTF pivot)."),
            # Edge-specific (mean-reversion)
            ConfirmationSpecV2(
                "C_EXHAUSTION_EVIDENCE",
                "Require exhaustion proxy: extension elevated (pct_change high) AND participation shows instability (e.g., RVOL spike then stall) OR failed hold at key level.",
            ),
            ConfirmationSpecV2(
                "C_ROTATIONAL_REGIME_REQUIRED",
                "Mean-reversion entries allowed only when intraday structure is rotational/two-sided (regime_tag preferred); veto trend-day proxies. Future mapping target: computed regime_tag upstream.",
            ),
            ConfirmationSpecV2(
                "C_VOLATILITY_REGIME_FILTER",
                "Veto volatility-expansion directional regime unless Tier A + explicit special exception with reduced size and tighter stop/time constraints.",
            ),
            ConfirmationSpecV2(
                "C_OVEREXTENSION_THRESHOLD",
                "Quantified overextension: pct_change>=12% qualifies as extended; pct_change>=40% enters too-hot caution. Evaluate only when dollar_volume>=20M liquidity gate is satisfied.",
            ),
            ConfirmationSpecV2(
                "C_ORDERFLOW_SHIFT_PROXY",
                "Required exhaustion evidence: RVOL spike then stall/deceleration, failure to print new highs/lows after impulse, rejection at key level with momentum loss. If no exhaustion proxy -> NO TRADE. Upstream fields target: momentum_state,rejection_tag.",
            ),
            ConfirmationSpecV2(
                "C_TREND_STRENGTH_VETO",
                "NO_TRADE if tape is strongly trending against the mean-reversion thesis (proxy: RVOL extremely high with continued extension and no rejection).",
            ),
            ConfirmationSpecV2(
                "C_REGIME_GATE",
                "Regime gate for mean reversion: NO_TRADE if halted=True, spread_pct>0.65%, dollar_volume<20M, or dead tape; "
                "CAUTION if RVOL>6.0 with pct_change>40 (too hot) or OPENING_FAST phase; NORMAL otherwise. "
                "Entries blocked in NO_TRADE; restricted in CAUTION; fully permitted only in NORMAL.",
            ),
            ConfirmationSpecV2(
                "C_CONVICTION_TIER",
                "Tier A requires: clean rejection at key level + stable spread + liquidity + reclaim/acceptance evidence; "
                "Tier B requires partial evidence; Tier C is probe-only or no-trade depending on regime gate.",
            ),
            ConfirmationSpecV2(
                "C_TOO_HOT_TO_FADE_CEILING",
                "Hard veto: pct_change>60% AND rvol>8.0 => NO TRADE for new entries; allow only risk-off management if already in position.",
            ),
            ConfirmationSpecV2(
                "C_CLUSTER_EXPOSURE_LIMIT",
                "Correlation/cluster governance: cap correlated basket loading and same-theme stacking using sector/correlation_group metadata when available.",
            ),
            ConfirmationSpecV2(
                "C_BORROW_AVAILABLE_FOR_SHORTS",
                "Short entries require shortable=True and locate_ok=True when applicable; if borrow_rate>15% reject short or reduce conviction tier by one.",
            ),
            ConfirmationSpecV2(
                "C_NEWS_TIMING_GUARD",
                "Block fades if high-impact news timestamp is within last 5 minutes (news_age_seconds<300 or equivalent from news_timestamp_utc).",
            ),
            ConfirmationSpecV2(
                "C_EOD_ENTRY_CUTOFF",
                "RTH end-of-day guard: no new entries in last 15 minutes before close; requires upstream session clock source.",
            ),
            ConfirmationSpecV2(
                "C_CATALYST_OPTIONAL_CONTEXT",
                "Catalyst is optional; if present, it explains the move and helps avoid fading strong fresh catalyst too early.",
                required=False,
            ),
        ),
    ),

    # ----------------------------
    # Structure model
    # ----------------------------
    structure_model=StructureModelV2(
        levels=(
            "PM_HIGH",
            "PM_LOW",
            "OPENING_RANGE_HIGH",
            "OPENING_RANGE_LOW",
            "VWAP",
            "DAY_HIGH",
            "DAY_LOW",
            "PRIOR_DAY_HIGH",
            "PRIOR_DAY_LOW",
            "PRIOR_CLOSE",
        ),
        zones=(
            "VALUE_REVERSION_ZONE",
            "OPENING_RANGE_ZONE",
            "EXHAUSTION_RISK_ZONE",
            "NO_REENTRY_COOLDOWN_ZONE",
        ),
        notes=(
            "P03 is anchor-driven: VWAP/OR/prior close/HTF pivots are explicit anchors. "
            "Structure decides where reversion is valid and where trend dominates."
        ),
    ),

    # ----------------------------
    # Position management / trailing / exits
    # ----------------------------
    position_management=PositionManagementV2(
        allow_scale_in=True,
        max_adds_per_position=1,
        allow_partials=True,
        averaging_down_allowed=False,
        notes=(
            "Mean reversion scaling is restricted: at most 1 add and only after reclaim/acceptance. "
            "No averaging down into invalidation. Partials are standard on first snapback impulse."
        ),
    ),
    trailing_model=TrailingModelV2(
        rules=(
            TrailingRuleV2(
                "TRAIL_TO_ANCHOR",
                "After snapback begins and reclaims anchor",
                "Trail stop to VWAP/anchor + last pivot to protect mean reversion thesis.",
            ),
            TrailingRuleV2(
                "TRAIL_AFTER_PARTIAL",
                "After first partial",
                "Tighten stop to reduce giveback; mean-reversion edge is time-sensitive.",
            ),
        )
    ),
    exit_model=ExitModelV2(
        rules=(
            ExitRuleV2("X_HARD_INVALIDATION", "Anchor reclaim fails or key invalidation level breached", "Exit full position immediately."),
            ExitRuleV2("X_FAILED_RECLAIM", "Reclaim then immediate loss with opposing participation", "Exit at least 50% immediately; evaluate flatten."),
            ExitRuleV2("X_TIME_STOP_FAST", "No snapback progress within 5 one-minute bars", "Flatten and recycle capital."),
            ExitRuleV2("X_TIME_STOP_SLOW", "No snapback progress within 2 five-minute bars", "Flatten and recycle capital."),
            ExitRuleV2("X_TARGET_MEAN", "Price reaches VWAP / prior close / defined mean target", "Take systematic partials; tighten stop."),
            ExitRuleV2("X_MAX_TIME_IN_TRADE", "Position duration exceeds 20 minutes unless already at/near target with protected stop", "Flatten remaining position."),
        )
    ),
    mean_reversion_extension=StrategyDomainExtensionSurfaceV2(
        min_extension_pct=12.0,
        too_hot_extension_pct=40.0,
        hard_veto_extension_pct=60.0,
        hard_veto_rvol=8.0,
        liquidity_gate_field="dollar_volume",
        liquidity_gate_min=20_000_000.0,
        notes="Extension thresholds are deterministic defaults and only evaluated when liquidity gate passes.",
    ),
    initial_stop_model=InitialStopModelV2(
        invalidation_reference="reclaim_low_or_pivot_or_anchor_loss",
        buffer_pct=0.15,
        min_buffer_ticks=1,
        rule="Initial stop always beyond invalidation structure: anchor ± max(0.15%, one spread/tick equivalent).",
        notes="Initial stop is structure-based only; discretionary stop placement is disallowed.",
    ),
    target_hierarchy_model=TargetHierarchyModelV2(
        priority_targets=("VWAP", "MIDPOINT", "PRIOR_CLOSE", "HTF_PIVOT_OR_DAY_MIDPOINT"),
        selection_law="Use first valid target in hierarchy; advance to next only after partial/confirmation.",
        notes="Deterministic target hierarchy for mean-reversion exits.",
    ),

    # ----------------------------
    # Safety model
    # ----------------------------
    safety_model=SafetyModelV2(
        rules=(
            SafetyRuleV2("S_HALT_GUARD", "halted=True or halt/resumption unstable", "Block entries; require stabilization window post-resume."),
            SafetyRuleV2("S_DATA_DEGRADATION", "Missing/stale required fields", "Pause entries for 3 cycles and emit degradation artifact."),
            SafetyRuleV2("S_SPREAD_SHOCK", "spread_pct exceeds cap by >50%", "No-new-entry throttle; open positions managed risk-off only."),
            SafetyRuleV2("S_MEAN_REVERSION_FAIL_STREAK", "Two consecutive mean-reversion failures", "Reduce size tier and require Tier A only for next N opportunities."),
            SafetyRuleV2("S_ADVERSE_MOVE_GUARD", "Price moves adversely by >0.35% during confirmation->order placement window", "Cancel/reject entry; re-evaluate on next cycle only."),
            SafetyRuleV2("S_SPREAD_WIDEN_DURING_ENTRY", "spread_pct widens by >0.20% absolute or limit would cross widened spread tolerance", "Reject entry and require spread normalization for 2 cycles."),
            SafetyRuleV2("S_GLOBAL_COOLDOWN_AFTER_LOSSES", "Two strategy-level stop-losses", "Pause new entries for 20 minutes; risk-reduction actions remain enabled."),
            SafetyRuleV2("S_SYMBOL_COOLDOWN_AFTER_STOP", "Single symbol stop-loss event", "Cooldown symbol for next 3 evaluation cycles before re-entry allowed."),
        )
    ),

    # ----------------------------
    # Stock selection law (P03-specific)
    # ----------------------------
    stock_selection_law=StockSelectionLawV2(
        price_model=PriceModelV2(
            min_price=2.0,
            max_price=200.0,
            preferred_upper_bound=50.0,
            reject_sub_dollar_rule=True,
            rationale_commentary=(
                "P03 requires liquidity and stable execution; sub-$1 noise is excluded. "
                "Very high-priced names are allowed but must still satisfy dollar-volume and spread requirements."
            ),
            calibration_notes="Deterministic defaults pending replay calibration.",
        ),
        gap_model=GapModelV2(
            hard_gap_threshold=2.0,
            soft_gap_threshold=1.0,
            percent_change_ranking_law="Pct_change is used to detect extension/exhaustion candidates; not a continuation edge.",
            gap_vs_pct_change_distinction="Gap is context near the open; pct_change remains a session-wide extension proxy.",
            calibration_notes="Deterministic defaults pending replay calibration.",
        ),
        volume_model=VolumeModelV2(
            min_total_volume=500_000,
            min_premarket_volume=0,
            dollar_volume_min=20_000_000.0,
            liquidity_commentary="Mean reversion needs deep liquidity; dollar_volume is a hard gate (from v1).",
            calibration_notes="Deterministic defaults pending replay calibration.",
        ),
        relative_volume_model=RelativeVolumeModelV2(
            rvol_minimum=1.5,
            calibration_commentary="RVOL minimum from v1 ensures sufficient participation for snapback execution.",
            calibration_notes="Deterministic defaults pending replay calibration.",
        ),
        float_model=FloatModelV2(
            float_max_millions=200.0,
            float_preferred_zone="30M-200M: tradable rotation without micro-noise; aligns with v1 float_max_millions.",
            float_explosive_zone="<30M allowed only under strict spread/liquidity gates (not primary subset).",
            inverse_weighting_in_ranking=True,
            float_data_sources=("YAHOO", "FINVIZ", "NASDAQ"),
            ibkr_not_primary_reason="IBKR feed is not canonical for corporate float metadata accuracy.",
            cache_policy_commentary="Float cache updates daily premarket; stale float incurs ranking penalty (not hard exclusion).",
            calibration_notes="Deterministic defaults pending replay calibration.",
        ),
        catalyst_model=CatalystModelV2(
            require_catalyst=False,
            catalyst_quality_levels=("SEC_FILINGS", "EARNINGS", "GUIDANCE", "MACRO", "NEWSWIRE"),
            internal_news_engine_primary=True,
            rss_fast_list_support=True,
            liquidity_proxy_when_uncertain=True,
            commentary=(
                "Catalyst is optional (v1). If catalyst implies strong continuation, trend-strength veto should block fades."
            ),
        ),
    ),

    # ----------------------------
    # Liquidity sanity + ranking weights
    # ----------------------------
    liquidity_sanity_model=LiquiditySanityModelV2(
        spread_max_pct=0.65,
        halt_policy="If halted=True (v1 allow_halts=False) or resumption instability is detected, block entries and require stabilization + structure revalidation.",
        ssr_handling="SSR allowed (v1 allow_ssr=True). Short enablement still requires separate governance and borrow checks.",
        execution_feasibility_commentary="Candidates violating spread cap are removed from eligibility regardless of rank.",
        calibration_notes="Deterministic defaults pending replay calibration.",
    ),
    ranking_model=RankingModelV2(
        # P03 ranks for tradable snapback quality, not continuation.
        weight_pct_change=0.20,        # extension proxy
        weight_rvol=0.12,              # enough participation to revert
        weight_float_inverse=0.08,     # mild preference
        weight_catalyst=0.05,          # context only
        liquidity_penalty=0.55,        # very heavy: avoid illiquid mean-reversion traps
        ranking_commentary=(
            "P03 ranks for mean-reversion feasibility: extension gets attention, but liquidity/executability dominates. "
            "Liquidity penalty is intentionally heavy to avoid false positives; catalyst is context only."
        ),
        calibration_notes="Weights are deterministic defaults pending replay optimization.",
    ),

    # ----------------------------
    # Data requirements
    # ----------------------------
    data_requirements=DataRequirementsV2(
        required_fields=(
            "symbol",
            "last_price",
            "pct_change",
            "volume",
            "rvol",
            "spread_pct",
            "session_label",
            "halted",
        ),
        optional_fields=(
            "news_catalyst",
            "float_shares",
            "float_millions",
            "short_interest_pct",
            "borrow_rate",
            "shortable",
            "locate_ok",
            "regime_tag",
            "news_timestamp_utc",
            "news_age_seconds",
            "sector",
            "correlation_group",
            "vwap_distance_pct",
            "anchor_distance_pct",
            "intraday_atr",
            "atr_pct",
            "momentum_state",
            "rejection_tag",
            "updated_at",
            "premarket_volume",
            "dollar_volume",
            "ssr",
        ),
        notes=(
            "Required fields must match canonical candidate adapter names. "
            "Legacy aliases (spread_bps/session_phase/halt_status) must be normalized upstream. D10.C03 deterministic doctrine: action codes are PAUSE "
            "(defer evaluation for this cycle and re-check next cycle), REJECT (drop symbol from this cycle's entry consideration), "
            "ABORT (halt the entire strategy cycle and emit cycle_abort artifact), and DEGRADE (continue only with fallback-safe "
            "logic while preserving risk-reduction/exits). Missing required market data for any candidate -> REJECT symbol immediately; "
            "if missing required fields affects >=20% of watchlist in a cycle -> ABORT cycle. Market snapshot retrieval failure for a "
            "single symbol -> PAUSE symbol for up to 2 consecutive cycles then REJECT until a fresh snapshot arrives; snapshot failure "
            "for the scanner/watchlist root dataset -> ABORT cycle. IBKR connectivity failure (scanner or market data transport unavailable) "
            "-> ABORT cycle immediately; allow exits/risk-reduction only. Volume data unavailable (volume or rvol missing/stale) -> "
            "REJECT symbol for entry; DEGRADE allowed only for managing already-open positions with no new entries. Spread data unavailable "
            "(spread_pct missing/stale) -> REJECT symbol for entry; no spread-implied fallback is permitted. Partial data state "
            "(all required fields present but one or more optional fields missing) -> DEGRADE by applying optional-field-neutral ranking and "
            "normal risk caps; if partial state persists >5 consecutive cycles for a symbol, REJECT symbol until optional fields recover."
        ),
    ),

    # ----------------------------
    # Premarket preparation
    # ----------------------------
    premarket_preparation=PremarketPreparationModelV2(
        required_levels=(
            PremarketLevelSpecV2("PM_HIGH", "Premarket high for extension/exhaustion context."),
            PremarketLevelSpecV2("PM_LOW", "Premarket low for flush/reversal context."),
            PremarketLevelSpecV2("PRIOR_DAY_HIGH", "Prior-day high for HTF resistance / fade context."),
            PremarketLevelSpecV2("PRIOR_DAY_LOW", "Prior-day low for downside failure context."),
            PremarketLevelSpecV2("PRIOR_CLOSE", "Prior close for gap-fill and mean target context."),
        ),
        required_filters=(
            PremarketFilterSpecV2("LIQUIDITY", "Liquidity and dollar-volume minima must be satisfied."),
            PremarketFilterSpecV2("EXECUTABILITY", "Spread and halt-state checks must be satisfied before handoff."),
        ),
        optional_filters=(
            PremarketFilterSpecV2("CATALYST_CONTEXT", "Catalyst context informs trend-strength veto risk.", required=False),
            PremarketFilterSpecV2("EXTENSION_TAG", "Tag extension candidates for possible mean-reversion watchlist.", required=False),
        ),
        room_to_run_policy=(
            "P03 requires room-to-mean: entries are only valid when there is space to revert toward VWAP/prior close "
            "without immediate structural obstruction."
        ),
        notes="Premarket preparation tags extension/anchors and enforces executability; no discretionary shortcuts.",
    ),

    # ----------------------------
    # Intrabar execution doctrine (phased)
    # ----------------------------
    intrabar_execution=IntrabarExecutionModelV2(
        phase_specs=(
            IntrabarPhaseSpecV2(
                "OPENING_FAST",
                "Opening Fast",
                "High volatility; mean-reversion entries are restricted and must use strict confirmation stack.",
                "Prefer OPENING_FLUSH_REVERSAL only; fades require strong exhaustion evidence and strict time-stop.",
            ),
            IntrabarPhaseSpecV2(
                "MIDDAY_NORMAL",
                "Midday Normal",
                "More stable; mean-reversion snaps to VWAP are highest quality if liquidity is stable.",
                "VWAP_SNAPBACK_REVERSION and GAP_FILL_PULLBACK are primary families.",
            ),
            IntrabarPhaseSpecV2(
                "LATE_DAY_SLOW",
                "Late Day Slow",
                "Liquidity transitions; prioritize exits/partials and avoid fresh fades unless Tier A only.",
                "New entries restricted; risk reduction remains fully active.",
            ),
        ),
        timeframe_map=(
            IntrabarTimeframeMapV2(
                "OPENING_FAST",
                ("15MIN", "5MIN", "1MIN"),
                ("5MIN", "1MIN"),
                ("10SEC", "1MIN"),
                "Fast monitoring: intrabar exits allowed; entries still require 1MIN acceptance evidence.",
            ),
            IntrabarTimeframeMapV2(
                "MIDDAY_NORMAL",
                ("15MIN", "5MIN", "1MIN"),
                ("5MIN", "1MIN"),
                ("1MIN",),
                "Candle-close confirmation preferred; intrabar override is safety exits only.",
            ),
            IntrabarTimeframeMapV2(
                "LATE_DAY_SLOW",
                ("15MIN", "5MIN"),
                ("5MIN",),
                ("1MIN",),
                "Late-day: prioritize exits/partials; new entries require Tier A only and NORMAL/CAUTION gating.",
            ),
        ),
        cadence_rules=(
            IntrabarCadenceRuleV2(
                "CADENCE_OPENING",
                ("OPENING_FAST",),
                "Evaluate 10SEC risk conditions each cycle; reevaluate entry stack on each 1MIN close.",
            ),
            IntrabarCadenceRuleV2(
                "CADENCE_MIDDAY",
                ("MIDDAY_NORMAL",),
                "Evaluate on 1MIN cadence with 5MIN anchor checkpoint; enforce time-stops strictly.",
            ),
            IntrabarCadenceRuleV2(
                "CADENCE_LATE",
                ("LATE_DAY_SLOW",),
                "Risk-reduction cadence; avoid fresh trades near close windows.",
            ),
        ),
        symbol_rotation_law=SymbolRotationLawV2(
            doctrine=(
                "Rotate focus toward symbols with clear anchors (VWAP/prior close/OR levels), stable spreads, and exhaustion evidence. "
                "Deprioritize symbols under halt/data/safety throttles or strong trend-strength veto."
            ),
            prioritization_rules=(
                "Prioritize highest mean-reversion feasibility score after liquidity penalty.",
                "Do not rotate into symbols under halt/data/safety throttles.",
                "Cap active focus count to preserve deterministic execution quality.",
            ),
            rotation_triggers=(
                "Current focus loses anchor validity (VWAP/level reclaim fails).",
                "Spread/liquidity drifts outside executable thresholds.",
                "Alternative symbol has materially better mean-reversion score and NORMAL regime.",
            ),
        ),
        safety_throttles=(
            IntrabarSafetyThrottleV2(
                "THROTTLE_NEWS_SHOCK",
                "Unscheduled news shock with volatility disorder",
                "Pause new entries for 3 cycles; allow only risk-reduction actions.",
            ),
            IntrabarSafetyThrottleV2(
                "THROTTLE_SPREAD_BLOWOUT",
                "spread_pct exceeds configured cap",
                "Block entries until spread normalizes for 2 consecutive cycles.",
            ),
            IntrabarSafetyThrottleV2(
                "THROTTLE_HALT_RESUME",
                "halted transitions from true to false",
                "Require 5-minute stabilization and structure revalidation before re-enabling entries.",
            ),
            IntrabarSafetyThrottleV2(
                "THROTTLE_DATA_DEGRADATION",
                "Required fields stale/missing",
                "Pause entries for 3 cycles and emit diagnostics; exits remain authorized.",
            ),
        ),
        setup_family_relationship=(
            "OPENING_FLUSH_REVERSAL dominates OPENING_FAST; VWAP_SNAPBACK_REVERSION and GAP_FILL_PULLBACK dominate MIDDAY_NORMAL; "
            "HOD_FADE_EXHAUSTION is restricted and requires strongest evidence; FAILED_RECLAIM_RISK_OFF is active in all phases. "
            "Long/short symmetry governance: VWAP_SNAPBACK_REVERSION and OPENING_FLUSH_REVERSAL are long-first with shorts disabled during one-sided bullish trend-day regime; "
            "HOD_FADE_EXHAUSTION and GAP_FILL_PULLBACK may short only when borrow/locate checks pass and trend-strength veto is not active."
        ),
        notes=(
            "Intrabar model is explicit and deterministic. Intrabar override authority is limited to risk-reduction "
            "(emergency exits/partials), not discretionary new entries."
        ),
    ),

    notes=(
        "P03 StrategyPolicyV2 is mean-reversion specific and audit-ready: explicit anchors, exhaustion doctrine, "
        "trend-strength veto, conservative risk, deterministic time-stops, and institutional doctrine addenda "
        "(regime qualification, quantified extension, microstructure exhaustion proxy, structure-based initial stops, "
        "execution adverse-selection guards, too-hot-to-fade veto, correlation caps, cooldowns, borrow governance, "
        "news timing guard, and EOD entry cutoff)."
    ),
)
