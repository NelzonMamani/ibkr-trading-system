from src.strategy_policy_v2.policy_v2 import (
    CatalystModelV2,
    CandleAndVolumeEvidenceModelV2,
    ConfirmationSpecV2,
    DataRequirementsV2,
    ExecutionModelV2,
    FloatModelV2,
    GapModelV2,
    ExitModelV2,
    ExitRuleV2,
    IntentContractV2,
    LiquiditySanityModelV2,
    IntrabarCadenceRuleV2,
    IntrabarExecutionModelV2,
    IntrabarPhaseSpecV2,
    IntrabarSafetyThrottleV2,
    IntrabarTimeframeMapV2,
    ImpulseQualificationAndMeasurementLawV2,
    IntrabarExitOverrideLawV2,
    MomentumWeaknessAndExitLawV2,
    ModeSemanticsV2,
    PatternCatalogV2,
    PatternSpecV2,
    PremarketFilterSpecV2,
    PremarketLevelSpecV2,
    PremarketPreparationModelV2,
    PositionManagementV2,
    PullbackWeaknessTierModelV2,
    PriceModelV2,
    RankingModelV2,
    RelativeVolumeModelV2,
    RiskModelV2,
    SymbolRotationLawV2,
    SafetyModelV2,
    SafetyRuleV2,
    SessionReferenceLawV2,
    SessionSemanticsV2,
    SetupFamiliesV2,
    SetupFamilySpecV2,
    StrategyIdentityV2,
    StrategyPolicyV2,
    StockSelectionLawV2,
    StructuralImpulseDetectionModelV2,
    StructureModelV2,
    TrailingModelV2,
    TrailingRuleV2,
    TriggerEntrySpecV2,
    VolumeDominanceProxyModelV2,
    VolumeModelV2,
    TriggerModelV2,
)
from src.strategy_policy_v2.selection_plans import ScannerPlan


POLICY_V2 = StrategyPolicyV2(
    identity=StrategyIdentityV2(name="ROSS_MOMENTUM", strategy_id="P01"),
    selection_plan=ScannerPlan(
        universe_source="IBKR_TOP_GAINERS",
        ibkr_scan_code="TOP_PERC_GAIN",
        top_n=50,
        watchlist_limit_k=15,
        focus_limit_m=5,
        policy_name="ROSS_MOMENTUM",
        gating_profile="ROSS_MOMENTUM_5_PILLARS_AND_TRADABILITY",
        session_allowlist=("PRE", "RTH", "AH"),
    ),
    mode_semantics=ModeSemanticsV2(
        sim_notes="SIM allowed; strategy emits paper-safe decision/trade intents only.",
        paper_notes="PAPER allowed with same policy constraints as SIM.",
        read_only_notes="READ_ONLY permits selection/ranking artifacts but blocks executable order intents.",
        live_notes="LIVE semantics are documented in policy only; runtime wiring is intentionally deferred.",
    ),
    session_semantics=SessionSemanticsV2(
        sessions=("PRE", "RTH", "AH", "OVN"),
        market_closed_semantics="CLOSED phase maps to non-trading behavior; no new entries are permitted.",
    ),
    risk_model=RiskModelV2(
        max_position_pct=0.1,
        daily_loss_limit=0.02,
        max_open_positions=10,
        notes=(
            "Ross-specific risk constraints include max_consecutive_losses=3, optional max_trades_per_symbol=None, "
            "optional max_reentries_per_symbol=None, and risk-overlay filters (LONG-only, gap/float/rvol/confidence, "
            "cooldown, max attempts). Gap/halt/slippage are controlled via gates, structure stops, and explicit pause/halt rules."
        ),
    ),
    execution_model=ExecutionModelV2(
        preferred_order_types=("LIMIT",),
        allow_market_orders=False,
        allow_extended_hours=True,
        notes=(
            "Spec-only constraints: scanner/session gates run first; entries are breakout/reclaim triggers with structure stops. "
            "Routing constraints are intentionally declarative and not wired in this migration."
        ),
    ),
    intent_contract=IntentContractV2(
        emitted_intents=("DECISION_INTENT", "TRADE_INTENT", "RISK_DECISION"),
        emitted_artifacts=(
            "strategy_decision",
            "watchlist_selection",
            "focus_selection",
            "pattern_evaluation_summary",
            "risk_overlay_decision",
        ),
        notes="Ranking intent name for scanner selection is ROSS_MOMENTUM_STOCK_SELECTION.",
    ),
    setup_families=SetupFamiliesV2(
        families=(
            SetupFamilySpecV2("GAP_GO", "Gap & Go", "High RVOL catalyst runner breaks premarket/open levels.", ("DAILY", "5MIN", "1MIN", "10SEC")),
            SetupFamilySpecV2("ORB", "Opening Range Breakout", "Break and hold above opening range high.", ("5MIN", "1MIN", "10SEC")),
            SetupFamilySpecV2("FIRST_PULLBACK", "First Pullback / First Flag", "First controlled pullback after impulse for continuation.", ("5MIN", "1MIN", "10SEC")),
            SetupFamilySpecV2("MICRO_PULLBACK", "Micro Pullback", "2-3 candle weak pullback followed by reclaim trigger.", ("1MIN", "10SEC")),
            SetupFamilySpecV2("BULL_FLAG", "Bull Flag / Tight Flag", "Impulse plus tight consolidation breakout.", ("5MIN", "1MIN")),
            SetupFamilySpecV2("KEY_LEVEL_BREAK", "Break of Key Level", "Premarket high, HOD, whole/half dollar, prior day, or multi-day level break.", ("DAILY", "5MIN", "1MIN")),
            SetupFamilySpecV2("ABCD", "ABCD Continuation", "Measured move continuation after pullback.", ("5MIN", "1MIN")),
            SetupFamilySpecV2("CUP_HANDLE", "Cup & Handle", "Rounded base and handle breakout.", ("5MIN", "1MIN")),
            SetupFamilySpecV2("MOMENTUM_RECLAIM", "Momentum Reclaim", "Reclaim VWAP/EMA after shakeout then continue.", ("1MIN", "10SEC")),
            SetupFamilySpecV2("PREMARKET_HIGH_BREAK", "Premarket High Break", "Reclaim and hold above premarket high.", ("PRE", "RTH", "1MIN", "10SEC")),
            SetupFamilySpecV2("HALT_RESUME", "Halt Resume Continuation", "Post-halt continuation only when liquidity and structure stabilize.", ("1MIN", "10SEC")),
            SetupFamilySpecV2("PARABOLIC_EXHAUSTION", "Parabolic Exhaustion", "Exit/avoid family used to de-risk rather than initiate entries.", ("1MIN", "5MIN")),
            SetupFamilySpecV2("GAP_FILL", "Gap Fill Reversal", "Gap fills toward prior close then reverses; used mainly as caution/exit or selective reversal context.", ("PRE", "RTH", "5MIN", "1MIN")),
            SetupFamilySpecV2("GAP_CONTINUATION", "Gap Continuation", "Gap holds and continues after initial consolidation; continuation bias.", ("PRE", "RTH", "5MIN", "1MIN", "10SEC")),
            SetupFamilySpecV2("OPENING_DRIVE", "Opening Drive", "Strong open trend day start; aggressive early momentum regime.", ("RTH_OPEN", "1MIN", "10SEC")),
            SetupFamilySpecV2("OPENING_FAKEOUT", "Opening Fakeout / Failed ORB", "ORB break fails and reverses; avoid/bail logic.", ("RTH_OPEN", "1MIN", "10SEC")),
            SetupFamilySpecV2("CONSOLIDATION_BREAKOUT", "Consolidation Breakout", "Breakout from tight range with volume expansion.", ("5MIN", "1MIN", "10SEC")),
            SetupFamilySpecV2("FLAT_TOP_BREAKOUT", "Flat Top Breakout", "Repeated resistance tests then break; classic momentum continuation.", ("5MIN", "1MIN", "10SEC")),
            SetupFamilySpecV2("ASCENDING_TRIANGLE", "Ascending Triangle", "Rising lows into flat resistance then break.", ("5MIN", "1MIN")),
            SetupFamilySpecV2("PENNANT", "Pennant", "Tight coil after impulse then breakout continuation.", ("5MIN", "1MIN")),
            SetupFamilySpecV2("RANGE_BREAK", "Range / Rectangle Breakout", "Rectangle range resolves with breakout; range boundaries are key levels.", ("5MIN", "1MIN")),
            SetupFamilySpecV2("HOD_BREAK", "High of Day Break", "HOD break continuation; key Ross momentum behavior.", ("RTH", "1MIN", "10SEC")),
            SetupFamilySpecV2("EMA_PULLBACK", "EMA Pullback", "Pullback to EMA9/EMA20 then reclaim; continuation entry context.", ("5MIN", "1MIN", "10SEC")),
            SetupFamilySpecV2("VWAP_PULLBACK", "VWAP Pullback", "Pullback to VWAP then reclaim; continuation entry context.", ("5MIN", "1MIN", "10SEC")),
            SetupFamilySpecV2("THREE_BAR_PULLBACK", "Three-Bar Pullback", "Three-bar pullback continuation variant.", ("1MIN", "10SEC")),
            SetupFamilySpecV2("TREND_CONTINUATION_STAIR_STEP", "Trend Continuation (Stair-Step)", "Higher-lows continuation sequence.", ("5MIN", "1MIN")),
            SetupFamilySpecV2("SECOND_PULLBACK", "Second Pullback", "Second pullback continuation following first pullback.", ("5MIN", "1MIN", "10SEC")),
        )
    ),
    pattern_catalog=PatternCatalogV2(
        patterns=(
            PatternSpecV2("P_PREMKT_BREAK", "Premarket High Break", "EXECUTION", "Entry setup pattern implemented in registry."),
            PatternSpecV2("P_ORB", "Opening Range Breakout", "EXECUTION", "Entry setup pattern implemented in registry."),
            PatternSpecV2("P_MICRO_PULLBACK", "Micro Pullback", "EXECUTION", "Entry and re-entry continuation pattern."),
            PatternSpecV2("P_BULL_FLAG", "Bull Flag", "EXECUTION", "Continuation pattern after impulse."),
            PatternSpecV2("P_CONSOLIDATION_BREAK", "Consolidation Breakout", "EXECUTION", "Tight range break expansion."),
            PatternSpecV2("P_FAILED_BREAKOUT", "Failed Breakout", "RISK", "Failure warning pattern and short-side caution context."),
            PatternSpecV2("C_LONG_UPPER_WICK", "Long Upper Wick / Topping Tail", "SINGLE_CANDLE", "Pause/Halt warning evidence for topping risk."),
            PatternSpecV2("C_MARUBOZU", "Marubozu", "SINGLE_CANDLE", "Breakout strength evidence tag."),
            PatternSpecV2("C_ENGULFING", "Engulfing", "MULTI_CANDLE", "Momentum confirmation evidence tag."),
            PatternSpecV2("C_THREE_SOLDIERS_CROWS", "Three Soldiers / Crows", "MULTI_CANDLE", "Momentum or reversal evidence tag."),
            PatternSpecV2("P_GAP_FILL_REVERSAL", "Gap Fill Reversal", "RISK", "Gap fill reversal context."),
            PatternSpecV2("P_OPENING_DRIVE", "Opening Drive", "EXECUTION", "Strong open trend start."),
            PatternSpecV2("P_FAILED_ORB_FAKEOUT", "Failed ORB / Opening Fakeout", "RISK", "ORB fakeout context."),
            PatternSpecV2("P_HOD_BREAK", "High of Day Break", "EXECUTION", "HOD break continuation."),
            PatternSpecV2("P_RANGE_BREAKOUT", "Range / Rectangle Breakout", "EXECUTION", "Box/range breakout."),
            PatternSpecV2("P_FLAT_TOP_BREAKOUT", "Flat Top Breakout", "EXECUTION", "Repeated resistance then break."),
            PatternSpecV2("P_ASCENDING_TRIANGLE_BREAKOUT", "Ascending Triangle Breakout", "EXECUTION", "Rising lows into resistance."),
            PatternSpecV2("P_PENNANT_BREAK", "Pennant Break", "EXECUTION", "Pennant continuation breakout."),
            PatternSpecV2("P_EMA_PULLBACK", "EMA Pullback", "EXECUTION", "EMA9/20 pullback reclaim."),
            PatternSpecV2("P_VWAP_PULLBACK", "VWAP Pullback", "EXECUTION", "VWAP reclaim continuation."),
            PatternSpecV2("P_THREE_BAR_PULLBACK", "Three-Bar Pullback", "EXECUTION", "Three-bar pullback continuation."),
            PatternSpecV2("P_TREND_CONTINUATION_STAIR_STEP", "Trend Continuation (Stair-Step)", "EXECUTION", "Higher-lows continuation."),
            PatternSpecV2("P_SECOND_PULLBACK", "Second Pullback", "EXECUTION", "Second pullback continuation."),
            PatternSpecV2("P_LIQUIDITY_SWEEP_RECLAIM", "Liquidity Sweep Reclaim", "EXECUTION", "Stop-run then reclaim."),
            PatternSpecV2("P_CLIMAX_TOP", "Climax Top", "RISK", "Exhaustion/climax behavior."),
            PatternSpecV2("P_VOLUME_CLIMAX", "Volume Climax", "RISK", "Volume spike exhaustion context."),
        )
    ),
    trigger_model=TriggerModelV2(
        entries=(
            TriggerEntrySpecV2("T_MICRO_RECLAIM", "BREAKOUT_RECLAIM", "Enter on first green candle breaking last red high after 2-3 red pullback bars.", ("OPENING_DRIVE", "MIDDAY", "LATE_DAY")),
            TriggerEntrySpecV2("T_PULLBACK_HIGH_BREAK", "PULLBACK_CONTINUATION", "Enter on pullback high reclaim or break of prior candle high.", ("RTH", "PRE")),
            TriggerEntrySpecV2("T_ORB_BREAK", "OPENING_RANGE_BREAK", "Enter on break above opening range high with hold.", ("RTH_OPEN",)),
            TriggerEntrySpecV2("T_ORB_1M", "OPENING_RANGE_BREAK", "ORB 1-minute variant: break and hold above 1M opening range high; executes under OPENING_DRIVE intrabar law.", ("OPENING_DRIVE",)),
            TriggerEntrySpecV2("T_ORB_5M", "OPENING_RANGE_BREAK", "ORB 5-minute variant: break and hold above 5M opening range high; executes under OPENING_DRIVE intrabar law.", ("OPENING_DRIVE",)),
            TriggerEntrySpecV2("T_GAP_AND_GO_IMMEDIATE", "GAP_AND_GO_IMMEDIATE", "Immediate momentum continuation at/through PMH-ORH without requiring 1M candle close; intrabar entries allowed during OPENING_DRIVE.", ("OPENING_DRIVE",)),
            TriggerEntrySpecV2("T_STARTER_POSITION_ANTICIPATION", "STARTER_POSITION_ANTICIPATION", "Optional small starter position before full confirmation when catalyst+liquidity+structure align; spec-only and calibration dependent.", ("OPENING_DRIVE", "MORNING_MOMENTUM")),
            TriggerEntrySpecV2("T_BREAKOUT_OR_BAILOUT", "BREAKOUT_OR_BAILOUT", "Failure-fast doctrine: if breakout rejects/fails to hold trigger structure, bail out immediately and prevent hope-holding.", ("OPENING_DRIVE", "MORNING_MOMENTUM", "MIDDAY")),
            TriggerEntrySpecV2("T_KEY_LEVEL_BREAK", "LEVEL_BREAK", "Enter on break of PMH/HOD/flag high/whole-half dollar with momentum.", ("PRE", "RTH", "AH")),
            TriggerEntrySpecV2("T_RECLAIM", "VWAP_EMA_RECLAIM", "Enter on reclaim of VWAP/EMA9/EMA20 with continuation structure.", ("RTH", "AH")),
            TriggerEntrySpecV2("T_ORB_RETEST", "OPENING_RANGE_RETEST", "Enter on successful retest/hold of OR high after initial break.", ("OPENING_DRIVE", "MORNING_MOMENTUM")),
            TriggerEntrySpecV2("T_FLAG_BREAK", "FLAG_BREAK", "Enter on break above flag/coil high with volume expansion.", ("OPENING_DRIVE", "MORNING_MOMENTUM", "MIDDAY")),
            TriggerEntrySpecV2("T_FLAG_RECLAIM", "FLAG_RECLAIM", "Enter on reclaim of flag high after brief flush.", ("OPENING_DRIVE", "MORNING_MOMENTUM", "MIDDAY")),
            TriggerEntrySpecV2("T_HOD_BREAK", "HOD_BREAK", "Enter on high-of-day break with momentum confirmation.", ("RTH_OPEN", "OPENING_DRIVE", "MORNING_MOMENTUM", "POWER_HOUR")),
            TriggerEntrySpecV2("T_RANGE_BREAK", "RANGE_BREAK", "Enter on range boundary break with confirmation.", ("OPENING_DRIVE", "MORNING_MOMENTUM", "MIDDAY", "POWER_HOUR")),
            TriggerEntrySpecV2("T_ABCD", "ABCD_TRIGGER", "Enter on ABCD continuation trigger.", ("MORNING_MOMENTUM", "MIDDAY", "POWER_HOUR")),
            TriggerEntrySpecV2("T_MEASURED_MOVE", "MEASURED_MOVE", "Measured-move continuation trigger.", ("MORNING_MOMENTUM", "MIDDAY", "POWER_HOUR")),
            TriggerEntrySpecV2("T_LIQUIDITY_SWEEP_RECLAIM", "LIQUIDITY_SWEEP_RECLAIM", "Flush/stop-run then reclaim key level.", ("OPENING_DRIVE", "MORNING_MOMENTUM")),
        ),
        confirmations=(
            ConfirmationSpecV2("C_VOLUME_EXPANSION", "Breakout volume should exceed pullback/consolidation volume."),
            ConfirmationSpecV2("C_MACD_POSITIVE", "MACD is a confirmation feature when present; treat as calibration-weighted evidence rather than universally mandatory gating.", required=False),
            ConfirmationSpecV2("C_HOLD_ABOVE_STRUCTURE", "Price must hold above VWAP/EMA9/EMA20 for long bias in pullbacks."),
            ConfirmationSpecV2("C_RVOL_IN_PLAY", "Relative volume and in-play gates must pass for candidate eligibility."),
            ConfirmationSpecV2("C_NO_TOPPING", "No topping-tail hard reversal signal on monitored structure timeframe."),
            ConfirmationSpecV2("C_VOLUME_BAR_DOMINANCE", "Rising red volume during pullback/consolidation is selling-pressure dominance and should pause/bail per setup."),
            ConfirmationSpecV2("VOLUME_CONFIRM", "Baseline volume confirmation must be present for breakouts/continuations."),
            ConfirmationSpecV2("RELATIVE_VOLUME_CONFIRM", "Relative volume must confirm in-play attention."),
            ConfirmationSpecV2("SPREAD_CONFIRM", "Spread must remain within sanity bound for intended cadence."),
            ConfirmationSpecV2("LIQUIDITY_CONFIRM", "Liquidity prints must support execution feasibility."),
            ConfirmationSpecV2("LEVEL_HOLD", "Trigger level must hold after break/reclaim."),
            ConfirmationSpecV2("BREAK_AND_HOLD", "Break-and-hold confirmation required."),
            ConfirmationSpecV2("RETEST_CONFIRM", "Retest must hold and reclaim to validate continuation."),
            ConfirmationSpecV2("NO_PARABOLIC_EXHAUSTION", "No parabolic exhaustion at entry moment."),
            ConfirmationSpecV2("DATA_QUALITY_CONFIRM", "Required fields must be present."),
        ),
    ),
    session_reference_law=SessionReferenceLawV2(
        pct_change_reference=(
            "Percent-change law references prior close and remains valid in PRE/AH/CLOSED contexts where official RTH open is absent or not actionable."
        ),
        gap_reference=(
            "Gap law references session open versus prior close and is only meaningful around the open/RTH transition; it is not a generic CLOSED-session prep metric."
        ),
        closed_session_preparation_notes=(
            "During CLOSED preparation, prioritize prior-close percent-change ranking and catalyst context rather than labeling symbols as active 'gappers'."
        ),
    ),
    candle_and_volume_evidence=CandleAndVolumeEvidenceModelV2(
        evidence_tags=(
            "DOJI",
            "SHOOTING_STAR",
            "HAMMER",
            "LONG_UPPER_WICK",
            "MARUBOZU",
            "ENGULFING",
            "THREE_SOLDIERS_CROWS",
            "SPINNING_TOP",
            "TOPPING_TAIL",
            "CANDLE_OVER_CANDLE",
            "FIRST_NEW_HIGH",
            "VOLUME_CLIMAX",
            "STRONG_BULL_BODY",
            "STRONG_BEAR_BODY",
            "EXPANSION_CANDLE",
            "EXHAUSTION_WICK",
        ),
        volume_bar_dominance_law=(
            "Volume-bar dominance doctrine: rising red volume during pullback or consolidation indicates selling-pressure control; policy should pause adds and bail when reclaim/breakout thesis degrades."
        ),
        risk_exit_pause_semantics=(
            "DOJI implies indecision and reduced conviction, SHOOTING_STAR implies topping/rejection risk with pause-or-exit bias, and HAMMER implies reclaim potential only if follow-through confirms."
        ),
    ),
    momentum_weakness_and_exit=MomentumWeaknessAndExitLawV2(
        pullback_tiers=PullbackWeaknessTierModelV2(
            ideal_pullback_max=0.30,
            caution_pullback_max=0.40,
            hard_warning_pullback_max=0.50,
            behavior_by_tier=(
                "<=30% pullback is the strongest continuation tier when reclaim/volume confirm.",
                "30-40% pullback is still tradable but requires cleaner structure-hold behavior.",
                "40-50% pullback is caution territory: reduce aggression and tighten invalidation tolerance.",
                ">=50% pullback indicates weak momentum thesis; pause adds and bias toward bailout unless immediate reclaim proves otherwise.",
            ),
            intrabar_detection_notes=(
                "Weakness is detected on execution timeframes (10SEC in fast phases), and can trigger exits before the 1M candle closes."
            ),
            calibration_notes="Subject to empirical validation; 30/40/50 tiers are Ross-style calibration defaults.",
        ),
        volume_dominance=VolumeDominanceProxyModelV2(
            enable_proxy_thresholds=False,
            red_vs_green_volume_pause_ratio=1.0,
            red_vs_impulse_green_volume_bail_ratio=1.2,
            commentary=(
                "Red versus green volume bars are used as selling-pressure proxies: when red bars begin to dominate pullback/consolidation flow, "
                "continuation odds degrade and risk response should shift from add to protect/bail. "
                "Proxy ratios remain disabled by default to prevent false precision until calibrated."
            ),
            calibration_notes="Subject to empirical validation; proxy thresholds are doctrine knobs rather than fixed truths.",
        ),
        intrabar_exit_override=IntrabarExitOverrideLawV2(
            allowed_phases=("OPENING_DRIVE", "MORNING_MOMENTUM"),
            execution_timeframes=("10SEC",),
            doctrine=(
                "Breakout-or-bail doctrine: intrabar structure failure overrides candle-close confirmation authority in fast phases; "
                "the policy explicitly permits 10SEC exits before a 1M candle forms/closes to avoid hope-holding through reversals."
            ),
            override_examples=(
                "Breakout rejects and loses trigger level intrabar after initial push.",
                "Pullback exceeds hard-warning retrace tier while momentum stalls.",
                "Topping-tail rejection prints as red volume dominance expands.",
                "Key reclaim level (VWAP/EMA/PMH) fails intrabar before 1M confirmation.",
            ),
            calibration_notes="Subject to empirical validation; fast-phase override behavior should be validated with replay metrics.",
        ),
        candle_evidence_alignment_notes=(
            "Use CandleAndVolumeEvidenceModelV2 tags to contextualize weakness: DOJI = indecision, SHOOTING_STAR/long upper wick = rejection risk, "
            "HAMMER = potential reclaim only with follow-through confirmation."
        ),
        notes=(
            "Spec-only consolidation layer: codifies pullback weakness tiers, intrabar exit authority, and red-volume dominance proxies without runtime wiring changes. "
            "Gap/open behavior is judged at the open, while percent-change ranking remains a preparation-stage sorting signal."
        ),
    ),
    impulse_qualification=ImpulseQualificationAndMeasurementLawV2(
        structural_impulse_definition=(
            "Structural impulse is defined as the expansion leg from the last confirmed higher low to the most recent expansion high that has not yet been structurally invalidated."
        ),
        micro_impulse_definition=(
            "Micro impulse is defined as the breakout expansion from a trigger level (e.g., pullback high, ORB high, PMH) on execution timeframe (10SEC in fast phases)."
        ),
        retracement_calculation_basis=(
            "Retracement percentage is calculated as (impulse_high - current_price) / (impulse_high - impulse_low). Pullback tiers reference this structural range."
        ),
        entry_trigger_law=(
            "Primary micro-pullback entry: enter on first green candle that breaks the high of the previous red candle sequence during valid continuation context."
        ),
        stop_placement_law=(
            "Initial stop placement = low of pullback structure. Loss beyond pullback low invalidates continuation thesis."
        ),
        pullback_candle_structure_law=(
            "Red pullback candles should exhibit smaller bodies relative to the impulse green candle bodies. Expanding red bodies or long upper wicks degrade continuation probability."
        ),
        macd_preference_law=(
            "Prefer entries when MACD is positive or curling upward on structure timeframe (typically 1MIN; 5MIN for higher timeframe context). MACD is confirmation-weighted evidence, not universal gating."
        ),
        fifty_percent_reset_law=(
            "If retracement exceeds 50% of the structural impulse range, continuation thesis is considered weak. Bias shifts to bail-out and no re-entry until new structural impulse forms."
        ),
        timeframe_alignment_notes=(
            "Impulse and retracement are structure-based, not time-boxed. Evaluation is fractal across 5MIN, 1MIN, and 10SEC. Intrabar exit authority (10SEC) may trigger before 1MIN candle close."
        ),
        calibration_notes=(
            "30/40/50 pullback tiers reflect Ross-style empirical doctrine and require future replay/statistical validation."
        ),
        notes="Spec-only structural law. No runtime wiring or evaluator implementation in this PR.",
    ),
    structural_impulse_detection=StructuralImpulseDetectionModelV2(),


    structure_model=StructureModelV2(
        levels=(
            "HOD",
            "LOD",
            "PREMARKET_HIGH",
            "PREMARKET_LOW",
            "OPENING_RANGE_HIGH",
            "OPENING_RANGE_LOW",
            "VWAP",
            "EMA9",
            "EMA20",
            "PRIOR_DAY_HIGH",
            "PRIOR_DAY_LOW",
            "PRIOR_CLOSE",
            "MULTI_DAY_HIGH",
            "WHOLE_HALF_DOLLAR_LEVELS",
            "FLAG_HIGH_LOW",
            "PULLBACK_HIGH_LOW",
        ),
        zones=("BREAKOUT_LEVEL", "RECLAIM_ZONE", "CONSOLIDATION_RANGE", "IMPULSE_TO_PULLBACK_RETRACE_ZONE"),
        notes="Daily provides context; 5m validates setup; 1m/10s handle entry and risk monitoring.",
    ),
    position_management=PositionManagementV2(
        allow_scale_in=True,
        max_adds_per_position=0,
        allow_partials=True,
        averaging_down_allowed=False,
        notes=(
            "Adds are permitted only on fresh continuation structure (e.g., pullback re-entry). "
            "No hard max adds is encoded in v1; value 0 denotes uncapped-by-policy and controlled by risk engine/session conditions."
        ),
    ),
    trailing_model=TrailingModelV2(
        rules=(
            TrailingRuleV2("TRAIL_TO_PULLBACK_LOW", "After entry confirmation and first extension", "Trail under most recent pullback low/flag low."),
            TrailingRuleV2("TRAIL_TO_VWAP_EMA", "When continuation weakens or topping risk rises", "Tighten stop to VWAP/EMA9 structure."),
            TrailingRuleV2("TRAIL_ON_TOPPING_WARNING", "Upper-wick topping warning appears", "Pause adds and tighten stop aggressively."),
            TrailingRuleV2("TRAIL_POST_PARTIALS", "After partial profit taken", "Move stop toward break-even or structural higher-low as permitted."),
        )
    ),
    exit_model=ExitModelV2(
        rules=(
            ExitRuleV2("X_STRUCTURE_STOP", "Loss of pullback/flag/level structure", "Exit remaining position."),
            ExitRuleV2("X_VWAP_EMA_LOSS", "Loss of VWAP/EMA9 support shortly after setup", "Exit or de-risk immediately."),
            ExitRuleV2("X_FAILED_BREAKOUT", "Breakout fails and reclaims below trigger level", "Exit long and mark setup as failed."),
            ExitRuleV2("X_TOPPING_HALT", "Confirmed topping/reversal candle", "Halt new entries and flatten risk according to manager."),
            ExitRuleV2("X_TIME_SESSION", "Session closes or strategy enters CLOSED semantics", "No new entries; flatten open intraday risk per runtime risk controller."),
        )
    ),
    safety_model=SafetyModelV2(
        rules=(
            SafetyRuleV2("S_DATA_QUALITY", "Missing required market data fields", "Pause new entries until data requirements are restored."),
            SafetyRuleV2("S_SPREAD_LIQUIDITY", "Spread too wide or liquidity gate fails", "Reject candidate or pause symbol."),
            SafetyRuleV2("S_HALT_POLICY", "Volatility halt detected", "Disallow halt-chasing entries until resume structure confirms."),
            SafetyRuleV2("S_SSR_POLICY", "SSR active", "Allowed by selection policy but must be considered in execution feasibility checks."),
            SafetyRuleV2("S_CONSECUTIVE_LOSSES", "Max consecutive losses reached", "Stop trading (halt) for strategy cooling-off window."),
            SafetyRuleV2("S_CONNECTION_ISSUE", "Scanner/order connectivity degraded", "Emit non-trading diagnostics and block new executable intents."),
        )
    ),
    stock_selection_law=StockSelectionLawV2(
        price_model=PriceModelV2(
            min_price=1.0,
            max_price=20.0,
            preferred_upper_bound=10.0,
            reject_sub_dollar_rule=True,
            rationale_commentary=(
                "Ross momentum doctrine focuses on low-priced momentum names while avoiding sub-dollar instruments due to noise, "
                "manipulation risk, and poor execution quality. Preferred activity often clusters in the lower-price band even when "
                "the hard maximum extends higher."
            ),
            calibration_notes="Subject to empirical validation; current values reflect documented Ross doctrine.",
        ),
        gap_model=GapModelV2(
            hard_gap_threshold=10.0,
            soft_gap_threshold=7.0,
            percent_change_ranking_law="Higher percent change receives higher rank priority after hard-gate eligibility is satisfied.",
            gap_vs_pct_change_distinction=(
                "Gap threshold is an in-play eligibility gate, while percent change is a relative ranking accelerator among names "
                "already inside the tradable universe."
            ),
            calibration_notes="Subject to empirical validation; current values reflect documented Ross doctrine.",
        ),
        volume_model=VolumeModelV2(
            min_total_volume=1_000_000,
            min_premarket_volume=100_000,
            dollar_volume_min=5_000_000.0,
            liquidity_commentary=(
                "Total volume and premarket volume enforce baseline participation; dollar volume adds execution realism so nominal "
                "share prints do not mask thin liquidity."
            ),
            calibration_notes="Subject to empirical validation; current values reflect documented Ross doctrine.",
        ),
        relative_volume_model=RelativeVolumeModelV2(
            rvol_minimum=5.0,
            calibration_commentary=(
                "RVOL is isolated from raw volume: RVOL measures abnormal attention, while total/premarket volume measure base "
                "liquidity needed to execute momentum setups."
            ),
            calibration_notes="Subject to empirical validation; current values reflect documented Ross doctrine.",
        ),
        float_model=FloatModelV2(
            float_max_millions=20.0,
            float_preferred_zone="Preferred tier: low float names below roughly 10M shares often exhibit cleaner momentum responsiveness when other gates align.",
            float_explosive_zone="Ultra-low float explosive tier (roughly sub-5M) can produce the fastest expansions with elevated volatility-halt and slippage risk.",
            inverse_weighting_in_ranking=True,
            float_data_sources=("YAHOO", "FINVIZ", "NASDAQ"),
            ibkr_not_primary_reason=(
                "IBKR is not the primary float authority because float classifications can lag and may not capture rapid issuance "
                "updates with the consistency needed for premarket selection decisions."
            ),
            cache_policy_commentary=(
                "Float values should be cached with source attribution and refresh discipline to avoid stale single-source figures "
                "during fast-moving sessions."
            ),
            calibration_notes="Subject to empirical validation; current values reflect documented Ross doctrine.",
        ),
        catalyst_model=CatalystModelV2(
            require_catalyst=True,
            catalyst_quality_levels=("HIGH", "MEDIUM", "LOW", "UNCERTAIN"),
            internal_news_engine_primary=True,
            rss_fast_list_support=True,
            liquidity_proxy_when_uncertain=True,
            commentary=(
                "Catalyst is structural in Ross selection doctrine. Internal news intelligence is primary, RSS fast-list sources "
                "support speed, and when catalyst certainty is incomplete the policy demands stronger liquidity/price-action evidence "
                "rather than blind inclusion."
            ),
        ),
    ),
    liquidity_sanity_model=LiquiditySanityModelV2(
        spread_max_pct=1.5,
        halt_policy="Active halts disallow fresh entries; resume participation only after post-halt structure and liquidity reconfirm.",
        ssr_handling="SSR is permitted but treated as an execution feasibility modifier requiring tighter confirmation.",
        execution_feasibility_commentary=(
            "Liquidity sanity enforces executable conditions so setup quality is not evaluated in isolation from spread/print behavior."
        ),
        calibration_notes="Subject to empirical validation; current values reflect documented Ross doctrine.",
    ),
    ranking_model=RankingModelV2(
        weight_pct_change=0.35,
        weight_rvol=0.30,
        weight_float_inverse=0.20,
        weight_catalyst=0.15,
        liquidity_penalty=0.25,
        ranking_commentary=(
            "Ranking prefers strongest percent-change momentum and RVOL, boosts lower-float responsiveness, incorporates catalyst "
            "quality, and penalizes weak tradability."
        ),
        calibration_notes="Subject to empirical validation; current values reflect documented Ross doctrine.",
    ),
    data_requirements=DataRequirementsV2(
        required_fields=(
            "symbol",
            "session_label",
            "last_price",
            "pct_change",
            "volume",
            "rvol",
            "dollar_volume",
            "float_millions",
            "gate_checks",
            "candles_10s_1m_5m",
            "vwap",
            "ema9",
            "ema20",
            "premarket_high",
            "hod",
            "news_catalyst",
        ),
        optional_fields=(
            "bid",
            "ask",
            "spread_pct",
            "halted",
            "ssr",
            "macd",
            "l2_iceberg_signals",
            "session_open_price",
            "prior_close",
        ),
        notes="If required fields are absent, policy mandates pause/reject semantics rather than speculative execution. Session-reference and candle-evidence models are spec-only; optional fields use fallback behavior (e.g., MACD as non-blocking confirmation when unavailable).",
    ),
    premarket_preparation=PremarketPreparationModelV2(
        scan_focus=("GAPPERS", "TOP_PCT_GAINERS", "RELATIVE_VOLUME", "CATALYST_NEWS", "SYMpathy_SECTOR"),
        higher_timeframe_context=("DAILY", "WEEKLY"),
        required_levels=(
            PremarketLevelSpecV2("L_PREMARKET_HIGH", "Premarket high (PMH) — key breakout level and trigger context."),
            PremarketLevelSpecV2("L_PREMARKET_LOW", "Premarket low (PML) — risk boundary and failure context."),
            PremarketLevelSpecV2("L_PRIOR_CLOSE", "Prior close — gap reference anchor (session ref)."),
            PremarketLevelSpecV2("L_PRIOR_DAY_HIGH_LOW", "Prior day high/low — overhead supply and support zones."),
            PremarketLevelSpecV2("L_MULTI_DAY_LEVELS", "2–5 day highs/lows — breakout ceiling / room-to-run context."),
            PremarketLevelSpecV2("L_WHOLE_HALF_DOLLAR", "Whole/half dollar psych levels — common stall/break points."),
            PremarketLevelSpecV2("L_VWAP", "VWAP (intraday anchor) — reclaim/hold context."),
            PremarketLevelSpecV2("L_EMA9_EMA20", "EMA9/EMA20 (intraday trend) — pullback/continuation structure."),
            PremarketLevelSpecV2("L_EMA200_DAILY", "Daily EMA200 — major HTF resistance/support; room-to-run constraint."),
        ),
        required_filters=(
            PremarketFilterSpecV2(
                "F_CATALYST_REQUIRED",
                "A real catalyst must exist (news/earnings/sector move/upgrade). No catalyst => do not trade.",
                required=True,
            ),
            PremarketFilterSpecV2(
                "F_IN_PLAY_GAP_RVOL_FLOAT_PRICE",
                "Must satisfy Ross in-play gates: price range, gap%, RVOL, float ceiling, liquidity.",
                required=True,
            ),
            PremarketFilterSpecV2(
                "F_ROOM_TO_RUN_HTF",
                "Room-to-run must exist on DAILY/WEEKLY: avoid immediate overhead supply; ensure upside air above key levels.",
                required=True,
            ),
            PremarketFilterSpecV2(
                "F_EMA200_CONTEXT",
                "Check position vs DAILY EMA200: if below EMA200, require clear reclaim plan + room; if extended into EMA200, expect resistance/stalls.",
                required=True,
            ),
            PremarketFilterSpecV2(
                "F_OVERHEAD_SUPPLY_CHECK",
                "Identify overhead supply zones: prior day highs, multi-day highs, major moving averages, whole/half dollars.",
                required=True,
            ),
            PremarketFilterSpecV2(
                "F_SPREAD_LIQUIDITY_SANITY",
                "Premarket spread/liquidity sanity check: avoid symbols with unusable spread/prints.",
                required=True,
            ),
        ),
        optional_filters=(
            PremarketFilterSpecV2(
                "F_FLOAT_ROTATION",
                "Prefer low float momentum names; float rotation narrative can influence ranking.",
                required=False,
            ),
            PremarketFilterSpecV2(
                "F_SECTOR_SYMPATHY",
                "If sector/theme is moving (AI, EV, crypto miners), prefer sympathy names with clean levels.",
                required=False,
            ),
            PremarketFilterSpecV2(
                "F_ATR_RANGE_CONTEXT",
                "Daily ATR / typical range context: ensure realistic upside targets vs resistance.",
                required=False,
            ),
            PremarketFilterSpecV2(
                "F_NEWS_QUALITY",
                "Prefer high-quality catalysts (PR/SEC/major outlets) vs thin/rumour sources.",
                required=False,
            ),
        ),
        room_to_run_policy=(
            "Room-to-run means: from current price to next major resistance (multi-day high, prior day high, EMA200, whole dollar) "
            "there is sufficient distance to justify momentum continuation. If compressed into resistance, either skip or "
            "treat as scalp-only with reduced size/risk. EMA200 is treated as a major boundary: reclaiming it can be bullish; "
            "rejecting from it often stalls."
        ),
        notes=(
            "This model encodes Ross premarket due diligence: scan gappers/gainers, confirm catalyst, map HTF levels, "
            "validate room-to-run (incl EMA200), and only then proceed to intrabar execution (10SEC) during OPENING_DRIVE. This is spec-only; runtime wiring deferred."
        ),
    ),
    intrabar_execution=IntrabarExecutionModelV2(
        phase_specs=(
            IntrabarPhaseSpecV2(
                phase_id="PREMARKET_PREP",
                phase_name="Premarket Preparation",
                doctrine="Analyze DAILY/5M/1M context and prepare levels/watchlist only.",
                trading_intent_policy="No trading intents; preparation and gating only.",
            ),
            IntrabarPhaseSpecV2(
                phase_id="OPENING_DRIVE",
                phase_name="Opening Drive",
                doctrine="Aggressive momentum execution: structure from 5M+1M, entries/refinements on 10SEC with intrabar triggers.",
                trading_intent_policy="Micro-scalp rapid entry/exit loops are allowed when risk overlay and max consecutive losses constraints remain valid.",
            ),
            IntrabarPhaseSpecV2(
                phase_id="MORNING_MOMENTUM",
                phase_name="Morning Momentum",
                doctrine="Still aggressive after initial open; 10SEC execution remains permitted for continuation and reclaim triggers.",
                trading_intent_policy="Repeated attempts are allowed when setup quality and safety throttles remain green.",
            ),
            IntrabarPhaseSpecV2(
                phase_id="MIDDAY",
                phase_name="Midday",
                doctrine="Reduced aggression and lower cadence; prioritize cleaner confirmation over raw speed.",
                trading_intent_policy="Primary execution on 1M; 10SEC optional for precision-only entries/exits.",
            ),
            IntrabarPhaseSpecV2(
                phase_id="POWER_HOUR",
                phase_name="Power Hour",
                doctrine="Timeframe compression regime with slower cadence and stronger confirmation preference.",
                trading_intent_policy="5M plays the morning 1M role; 1M plays the morning 10SEC role.",
            ),
            IntrabarPhaseSpecV2(
                phase_id="LATE_DAY",
                phase_name="Late Day",
                doctrine="Timeframe compression continues into close; preserve selectivity and avoid overtrading.",
                trading_intent_policy="Execution cadence is slower than OPENING_DRIVE; prioritize high-quality continuation or reclaim only.",
            ),
            IntrabarPhaseSpecV2(
                phase_id="AFTER_HOURS",
                phase_name="After Hours",
                doctrine="If session semantics allow AH participation, trade conservatively with reduced cadence and higher safety constraints.",
                trading_intent_policy="Only allow intents that pass stricter liquidity/spread and operational safety checks.",
            ),
        ),
        timeframe_map=(
            IntrabarTimeframeMapV2(
                phase_id="PREMARKET_PREP",
                analysis_timeframes=("DAILY", "5MIN", "1MIN"),
                structure_timeframes=("DAILY", "5MIN", "1MIN"),
                execution_timeframes=(),
                candle_close_policy="Candle-close confirmation is for analysis only because this phase emits no trading intents.",
            ),
            IntrabarTimeframeMapV2(
                phase_id="OPENING_DRIVE",
                analysis_timeframes=("DAILY", "5MIN", "1MIN"),
                structure_timeframes=("5MIN", "1MIN"),
                execution_timeframes=("10SEC",),
                candle_close_policy="Do not require 1M candle close for Gap&Go/immediate momentum entries; intrabar 10SEC triggers are explicitly allowed.",
            ),
            IntrabarTimeframeMapV2(
                phase_id="MORNING_MOMENTUM",
                analysis_timeframes=("5MIN", "1MIN"),
                structure_timeframes=("5MIN", "1MIN"),
                execution_timeframes=("10SEC", "1MIN"),
                candle_close_policy="Intrabar trigger semantics remain valid on 10SEC; 1M close may be used when tape slows.",
            ),
            IntrabarTimeframeMapV2(
                phase_id="MIDDAY",
                analysis_timeframes=("5MIN", "1MIN"),
                structure_timeframes=("5MIN", "1MIN"),
                execution_timeframes=("1MIN", "10SEC"),
                candle_close_policy="Prefer candle-close confirmation on 1M for slower phases; use 10SEC only to refine price location.",
            ),
            IntrabarTimeframeMapV2(
                phase_id="POWER_HOUR",
                analysis_timeframes=("5MIN", "1MIN"),
                structure_timeframes=("5MIN", "1MIN"),
                execution_timeframes=("1MIN",),
                candle_close_policy="Timeframe compression: 5M carries the morning 1M structure role and 1M carries the morning 10SEC execution role.",
            ),
            IntrabarTimeframeMapV2(
                phase_id="LATE_DAY",
                analysis_timeframes=("5MIN", "1MIN"),
                structure_timeframes=("5MIN", "1MIN"),
                execution_timeframes=("1MIN",),
                candle_close_policy="Timeframe compression law remains in force; favor slower, confirmed executions and avoid OPENING_DRIVE cadence.",
            ),
            IntrabarTimeframeMapV2(
                phase_id="AFTER_HOURS",
                analysis_timeframes=("5MIN", "1MIN"),
                structure_timeframes=("5MIN", "1MIN"),
                execution_timeframes=("1MIN",),
                candle_close_policy="Conservative close-confirmation preference with strict spread/liquidity gating.",
            ),
        ),
        cadence_rules=(
            IntrabarCadenceRuleV2(
                rule_id="C_CONTROL_BUY_CONTROL_CLOSE",
                applies_to_phases=("OPENING_DRIVE", "MORNING_MOMENTUM"),
                doctrine="Control buy / control close doctrine: rapid entry/exit loops are allowed while risk overlay, stop discipline, and consecutive-loss guard remain active.",
            ),
            IntrabarCadenceRuleV2(
                rule_id="C_BURST_WINDOW",
                applies_to_phases=("OPENING_DRIVE",),
                doctrine="Burst trading is allowed during the first 15-60 minutes on 1-3 primary symbols; automation may concurrently manage up to focus_limit_m symbols under strict gating.",
            ),
            IntrabarCadenceRuleV2(
                rule_id="C_MIDDAY_SLOWDOWN",
                applies_to_phases=("MIDDAY", "POWER_HOUR", "LATE_DAY", "AFTER_HOURS"),
                doctrine="Cadence decelerates outside the morning drive: fewer attempts, stronger confirmation preference, and selective re-entry behavior.",
            ),
        ),
        symbol_rotation_law=SymbolRotationLawV2(
            doctrine="Trade the best 1-3 names, not everything; prioritize focus-list leaders while allowing automation to monitor multiple symbols with strict entry gating.",
            prioritization_rules=(
                "Prefer symbols already in focus list with strongest in-play alignment and clean structure.",
                "When several candidates qualify, allocate attention to the highest-quality momentum names first.",
            ),
            rotation_triggers=(
                "Rotate away when relative strength weakens, setup invalidates, or structure fails to reclaim/hold key levels.",
                "Rotate toward symbols showing cleaner continuation structure and execution feasibility.",
            ),
        ),
        safety_throttles=(
            IntrabarSafetyThrottleV2(
                throttle_id="T_SPREAD_LIQUIDITY_SANITY",
                trigger="Spread/liquidity sanity degrades for intended execution cadence.",
                behavior="Block micro-scalp rapid-fire intents until tradability returns to acceptable conditions.",
            ),
            IntrabarSafetyThrottleV2(
                throttle_id="T_HALT_INTERACTION",
                trigger="Halt risk, active halt, or unstable halt-resume tape during micro-scalp context.",
                behavior="Suspend rapid execution loops and require post-resume structure/liquidity validation before any continuation intent.",
            ),
            IntrabarSafetyThrottleV2(
                throttle_id="T_LATENCY_DEGRADATION",
                trigger="Connection/latency degradation detected for scanner, market data, or order path.",
                behavior="Block rapid-fire intents and degrade to non-trading diagnostics or slower confirmation-only behavior.",
            ),
            IntrabarSafetyThrottleV2(
                throttle_id="T_CANCEL_REPLACE_CHURN_GUARD",
                trigger="Cancel/replace churn indicates unstable quoting or excessive order management churn.",
                behavior="Apply churn guard to prevent hyperactive micro-scalp loops until execution stability is restored.",
            ),
        ),
        setup_family_relationship=(
            "Gap&Go, ORB, First Pullback, Bull Flag, ABCD, Momentum Reclaim, Premarket High Break, and related continuation families can all be executed via OPENING_DRIVE micro-scalp doctrine using 10SEC entries. "
            "Micro pullback is an execution tool used especially in the morning drive (not an afternoon-only concept); afternoon and late-day operation instead use timeframe compression and slower cadence."
        ),
        notes=(
            "Intrabar execution law is declarative and spec-only: it codifies phase-aware timeframe usage, candle-close rules, cadence, symbol rotation, and safety throttles without runtime wiring changes."
        ),
    ),
    notes=(
        "Spec-only full-law policy for P01 Ross Momentum. Gating is expected at scanner eligibility, "
        "pattern evaluation, and risk overlay stages; no runtime wiring changes are introduced here."
    ),
)
