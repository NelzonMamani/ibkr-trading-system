from src.strategy_policy_v2.policy_v2 import (
    CatalystModelV2,
    CandleAndVolumeEvidenceModelV2,
    ConfirmationSpecV2,
    DataRequirementsV2,
    ExecutionModelV2,
    ExitModelV2,
    ExitRuleV2,
    FloatModelV2,
    GapModelV2,
    ImpulseQualificationAndMeasurementLawV2,
    IntentContractV2,
    IntrabarCadenceRuleV2,
    IntrabarExecutionModelV2,
    IntrabarPhaseSpecV2,
    IntrabarSafetyThrottleV2,
    IntrabarTimeframeMapV2,
    LiquiditySanityModelV2,
    MicroToStructuralPromotionLawV2,
    ModeSemanticsV2,
    MomentumWeaknessAndExitLawV2,
    PatternCatalogV2,
    PatternSpecV2,
    PivotConfirmationModelV2,
    PositionManagementV2,
    PremarketFilterSpecV2,
    PremarketLevelSpecV2,
    PremarketPreparationModelV2,
    PriceModelV2,
    PullbackWeaknessTierModelV2,
    RankingModelV2,
    RelativeVolumeModelV2,
    RiskModelV2,
    SafetyModelV2,
    SafetyRuleV2,
    SessionReferenceLawV2,
    SessionSemanticsV2,
    SetupFamiliesV2,
    SetupFamilySpecV2,
    StockSelectionLawV2,
    StrategyIdentityV2,
    StrategyPolicyV2,
    StructuralImpulseDetectionModelV2,
    StructureModelV2,
    SymbolRotationLawV2,
    TrailingModelV2,
    TrailingRuleV2,
    TriggerEntrySpecV2,
    TriggerModelV2,
    VolumeDominanceProxyModelV2,
    VolumeModelV2,
    IntrabarExitOverrideLawV2,
)
from src.strategy_policy_v2.selection_plans import ScannerPlan


POLICY_V2 = StrategyPolicyV2(
    identity=StrategyIdentityV2(name="STATISTICAL_INTRADAY_MOMENTUM", strategy_id="P02"),
    selection_plan=ScannerPlan(
        universe_source="IBKR_TOP_GAINERS",
        ibkr_scan_code="TOP_PERC_GAIN",
        top_n=50,
        watchlist_limit_k=15,
        focus_limit_m=5,
        policy_name="STATISTICAL_INTRADAY_MOMENTUM",
        gating_profile="STATISTICAL_INTRADAY_MOMENTUM",
        session_allowlist=("PRE", "RTH", "AH"),
    ),
    mode_semantics=ModeSemanticsV2(
        sim_notes="SIM executes full policy gates and emits auditable decision artifacts.",
        paper_notes="PAPER mode mirrors SIM policy behavior with broker-safe intent output.",
        read_only_notes="READ_ONLY runs selection, setup, and risk evaluation but blocks executable intents.",
        live_notes="LIVE is permitted only when this policy and risk envelope are wired by runtime governance.",
    ),
    session_semantics=SessionSemanticsV2(
        sessions=("PRE", "RTH", "AH", "OVN", "CLOSED"),
        market_closed_semantics="CLOSED session blocks new entries and forces only risk-reducing actions.",
    ),
    risk_model=RiskModelV2(
        max_position_pct=0.08,
        daily_loss_limit=0.018,
        max_open_positions=6,
        notes=(
            "P02 risk envelope is deterministic: smaller max position than P01, bounded portfolio concurrency, "
            "and mandatory escalation after repeated momentum-failure exits."
        ),
    ),
    execution_model=ExecutionModelV2(
        preferred_order_types=("LIMIT", "STOP_LIMIT"),
        allow_market_orders=False,
        allow_extended_hours=True,
        notes=(
            "Execution remains price-controlled; extended-hours entries are allowed only when liquidity and spread confirmations are satisfied."
        ),
    ),
    intent_contract=IntentContractV2(
        emitted_intents=("DECISION_INTENT", "TRADE_INTENT", "RISK_DECISION"),
        emitted_artifacts=("strategy_decision", "setup_evaluation", "risk_snapshot", "exit_decision"),
        notes="All artifacts must include setup_family_id and trigger_id for audit traceability.",
    ),
    setup_families=SetupFamiliesV2(
        families=(
            SetupFamilySpecV2(
                "OPENING_CONTINUATION",
                "Opening Continuation",
                "Opening drive continuation after break-and-hold with strong participation.",
                ("15MIN", "5MIN", "1MIN", "10SEC"),
            ),
            SetupFamilySpecV2(
                "VWAP_RECLAIM_CONTINUATION",
                "VWAP Reclaim Continuation",
                "Trend resumes after reclaiming VWAP and holding through a retest.",
                ("15MIN", "5MIN", "1MIN", "10SEC"),
            ),
            SetupFamilySpecV2(
                "RANGE_EXPANSION_BREAKOUT",
                "Range Expansion Breakout",
                "Compression resolves into directional expansion with RVOL confirmation.",
                ("15MIN", "5MIN", "1MIN"),
            ),
            SetupFamilySpecV2(
                "PULLBACK_CONTINUATION",
                "Pullback Continuation",
                "Controlled pullback in established impulse resumes with structural hold confirmation.",
                ("5MIN", "1MIN", "10SEC"),
            ),
            SetupFamilySpecV2(
                "FAILED_BREAK_RISK_OFF",
                "Failed Break Risk-Off",
                "Failure family used for exit/no-reentry governance after break-and-hold rejection.",
                ("5MIN", "1MIN", "10SEC"),
            ),
        )
    ),
    pattern_catalog=PatternCatalogV2(
        patterns=(
            PatternSpecV2("PATTERN_OPEN_DRIVE", "Opening Drive Continuation", "MULTI_CANDLE", "Entry pattern for OPENING_CONTINUATION"),
            PatternSpecV2("PATTERN_VWAP_RECLAIM", "VWAP Reclaim and Hold", "MULTI_CANDLE", "Entry pattern for VWAP_RECLAIM_CONTINUATION"),
            PatternSpecV2("PATTERN_COMPRESSION_BREAK", "Compression to Expansion", "MULTI_CANDLE", "Entry pattern for RANGE_EXPANSION_BREAKOUT"),
            PatternSpecV2("PATTERN_PULLBACK_RESUME", "Pullback Resume", "MULTI_CANDLE", "Entry pattern for PULLBACK_CONTINUATION"),
            PatternSpecV2("PATTERN_FAILED_BREAK", "Failed Break Risk-Off", "RISK", "Exit/no-reentry pattern for FAILED_BREAK_RISK_OFF"),
        )
    ),
    trigger_model=TriggerModelV2(
        entries=(
            TriggerEntrySpecV2(
                "T_OPENING_BREAK_HOLD",
                "BREAKOUT_CONTINUATION",
                "Break opening range high and hold above it for >=1 structure bar with RVOL>=2.0 and spread<=0.60%.",
                ("PRE", "RTH"),
            ),
            TriggerEntrySpecV2(
                "T_VWAP_RECLAIM_HOLD",
                "RECLAIM_CONTINUATION",
                "Reclaim VWAP then hold for >=2 execution bars while maintaining higher-low structure.",
                ("RTH", "AH"),
            ),
            TriggerEntrySpecV2(
                "T_RANGE_EXPANSION",
                "VOLATILITY_EXPANSION",
                "Break compression boundary with volume expansion >=1.8x recent baseline.",
                ("RTH",),
            ),
            TriggerEntrySpecV2(
                "T_PULLBACK_RESUME",
                "PULLBACK_CONTINUATION",
                "Pullback depth <=40% of impulse and resume via reclaim of continuation pivot.",
                ("RTH", "AH"),
            ),
            TriggerEntrySpecV2(
                "T_FAILED_BREAK_EXIT",
                "RISK_OFF",
                "Breakout fails and closes back inside prior range with participation fade; force de-risk behavior.",
                ("PRE", "RTH", "AH"),
            ),
        ),
        confirmations=(
            ConfirmationSpecV2("C_HTF_BIAS", "Higher timeframe (15MIN/5MIN) bias aligns with trigger direction."),
            ConfirmationSpecV2("C_LIQUIDITY_SPREAD", "Liquidity passes minimums and spread_pct <= configured spread max."),
            ConfirmationSpecV2("C_VOL_REGIME", "Volatility regime is compatible with continuation edge; avoid dead tape or shock disorder."),
            ConfirmationSpecV2("C_STRUCTURE_HOLD", "Break/reclaim level holds without immediate rejection in execution timeframe."),
            ConfirmationSpecV2("C_PARTICIPATION", "Volume and RVOL confirm participation relative to current session baseline."),
            ConfirmationSpecV2("C_DATA_FRESHNESS", "Candidate data freshness and required fields are valid at decision time."),
            ConfirmationSpecV2(
                "C_CATALYST_OPTIONAL_BOOST",
                "Catalyst presence is optional; when present it boosts ranking confidence but is not a hard gate.",
                required=False,
            ),
        ),
    ),
    session_reference_law=SessionReferenceLawV2(
        pct_change_reference="Percent-change references prior close for cross-session continuity.",
        gap_reference="Gap references current regular-session open versus prior close for opening context only.",
        closed_session_preparation_notes="CLOSED/OVN periods are preparation-only; no execution intents are emitted.",
    ),
    candle_and_volume_evidence=CandleAndVolumeEvidenceModelV2(
        evidence_tags=(
            "PARTICIPATION_EXPANSION",
            "HEALTHY_PULLBACK_LOW_RED_VOLUME",
            "EXHAUSTION_SPIKE",
            "FAILED_RECLAIM",
            "MOMENTUM_CONTINUATION",
            "MEAN_REVERSION_RISK",
        ),
        volume_bar_dominance_law=(
            "Participation evidence: green-volume dominance and rising RVOL on breaks/reclaims supports continuation ranking and entry gating. "
            "Exhaustion evidence: outsized climax volume with poor extension or immediate rejection increases mean-reversion risk and can pause new entries."
        ),
        risk_exit_pause_semantics=(
            "Evidence usage is explicit: continuation evidence can satisfy trigger confirmations; mean-reversion/exhaustion evidence does not auto-short, "
            "but invokes risk-off exits, no-add state, and optional safety pause for fresh entries."
        ),
    ),
    momentum_weakness_and_exit=MomentumWeaknessAndExitLawV2(
        pullback_tiers=PullbackWeaknessTierModelV2(
            ideal_pullback_max=0.30,
            caution_pullback_max=0.40,
            hard_warning_pullback_max=0.50,
            behavior_by_tier=(
                "<=30% retrace: continuation quality intact; entries/adds allowed with structure confirmation.",
                "30-40% retrace: reduced aggressiveness; require stronger confirmation stack before entry/add.",
                "40-50% retrace: warning tier; partial risk reduction and tighter invalidation stops required.",
                ">=50% retrace: momentum thesis statistically weak; transition to risk-off and wait for reset.",
            ),
            intrabar_detection_notes=(
                "Weakness is evaluated on 10SEC/1MIN execution frames; momentum failure can trigger exits before 5MIN confirmation."
            ),
            calibration_notes="Thresholds are governance defaults pending replay calibration for P02.",
        ),
        volume_dominance=VolumeDominanceProxyModelV2(
            enable_proxy_thresholds=True,
            red_vs_green_volume_pause_ratio=1.10,
            red_vs_impulse_green_volume_bail_ratio=1.30,
            commentary=(
                "If red pullback volume exceeds green continuation volume by pause ratio, suspend adds/entries. "
                "If bail ratio is exceeded with structure loss, classify as momentum failure and exit remaining risk."
            ),
            calibration_notes="Proxy ratios are deterministic policy defaults pending replay statistics.",
        ),
        intrabar_exit_override=IntrabarExitOverrideLawV2(
            allowed_phases=("OPENING_FAST", "MIDDAY_NORMAL", "LATE_DAY_SLOW"),
            execution_timeframes=("10SEC", "1MIN"),
            doctrine=(
                "Intrabar override authority is risk-reduction only: emergency exits/partials are allowed intrabar; "
                "new entries still require full trigger+confirmation semantics."
            ),
            override_examples=(
                "Failed break re-enters prior range with rising opposing volume.",
                "VWAP reclaim loses hold within two execution bars.",
                "Spread blowout or halt signal appears while position is open.",
                "Retracement crosses hard-warning tier and structure invalidates intrabar.",
            ),
            calibration_notes="Intrabar override is enabled for safety; response windows are deterministic and non-random.",
        ),
        candle_evidence_alignment_notes=(
            "Continuation evidence aligns with entry families OPENING_CONTINUATION, VWAP_RECLAIM_CONTINUATION, RANGE_EXPANSION_BREAKOUT, and PULLBACK_CONTINUATION. "
            "Mean-reversion/failed-break evidence maps to FAILED_BREAK_RISK_OFF exits and no-reentry cooldown."
        ),
        notes=(
            "Momentum failure mechanics: failed reclaim back into range plus participation fade equals risk-off. "
            "Time-stop doctrine uses 1MIN/5MIN progress windows, with partial-taking and stop tightening after extension."
        ),
    ),
    impulse_qualification=ImpulseQualificationAndMeasurementLawV2(
        structural_impulse_definition=(
            "Structural impulse requires directional expansion on 1MIN or 5MIN with range >=1.2x recent median bar range and RVOL support >=1.8."
        ),
        micro_impulse_definition=(
            "Micro impulse is 10SEC/1MIN acceleration that aligns with structural direction and breaks micro pivot without immediate rejection."
        ),
        retracement_calculation_basis=(
            "Retracement = (impulse_high - current_pullback_low)/(impulse_high - impulse_low) for long thesis; mirrored for shorts if enabled by runtime governance."
        ),
        entry_trigger_law=(
            "Accept entries on break-and-hold, reclaim-and-hold, or pullback resume only when impulse remains below 50% reset threshold and confirmations are satisfied."
        ),
        stop_placement_law=(
            "Initial stop anchors to structural invalidation (pivot low, VWAP hold-loss, or range re-entry), then tightens after >=1R extension."
        ),
        pullback_candle_structure_law=(
            "Preferred pullback candles show contracting range and reduced opposing volume; wide-range opposing candles invalidate add authority."
        ),
        macd_preference_law=(
            "MACD/oscillator alignment is a soft preference only; no mandatory dependency so policy remains deterministic without indicator feed coupling."
        ),
        fifty_percent_reset_law=(
            "Retracement >=50% marks impulse reset required: disable continuation entries until a new structural impulse and hold sequence forms."
        ),
        timeframe_alignment_notes=(
            "15MIN sets bias, 5MIN validates structure, 1MIN confirms trigger context, 10SEC supports execution-risk timing only."
        ),
        calibration_notes="Impulse and retracement thresholds are governance defaults pending replay calibration.",
        notes="P02 impulse doctrine is continuation-statistical, not Ross 5-pillar mimicry.",
    ),
    structural_impulse_detection=StructuralImpulseDetectionModelV2(
        structure_timeframe_by_phase={
            "OPENING_FAST": "1MIN",
            "MIDDAY_NORMAL": "5MIN",
            "LATE_DAY_SLOW": "5MIN",
        },
        micro_timeframe_by_phase={
            "OPENING_FAST": "10SEC",
            "MIDDAY_NORMAL": "1MIN",
            "LATE_DAY_SLOW": "1MIN",
        },
        pivot_confirmation=PivotConfirmationModelV2(
            pivot_left_bars=2,
            pivot_right_bars=2,
            reclaim_confirm_levels=("VWAP", "OPENING_RANGE_HIGH", "OPENING_RANGE_LOW", "DAY_HIGH", "DAY_LOW", "PM_HIGH", "PM_LOW"),
            min_reclaim_hold_bars=1,
            allow_intrabar_hint=True,
            notes=(
                "Level sources are explicit: VWAP, PMH/PML, ORH/ORL, day high/low, and prior-day anchors when available. "
                "Break-and-hold requires structure confirmation; failed break is rejection back through trigger level within failure window."
            ),
        ),
        promotion_law=MicroToStructuralPromotionLawV2(
            require_new_structure_high=True,
            require_hold_levels=("VWAP", "OPENING_RANGE_HIGH", "DAY_HIGH"),
            max_failure_window_bars=2,
            notes=(
                "Micro signals promote only after creating new structure high and holding key levels; rapid reclaim failure blocks promotion."
            ),
        ),
        impulse_low_rule="Impulse low is the last confirmed pivot low on structure timeframe before expansion starts.",
        impulse_high_rule="Impulse high is the highest confirmed high prior to pullback depth crossing caution tier.",
        invalidation_rules=(
            "Break-and-hold failure: close back inside prior range after breakout attempt.",
            "Loss of VWAP/reclaim anchor with opposing-volume dominance invalidates continuation.",
            "Retracement >=50% invalidates current impulse and requires reset.",
        ),
        reset_rules=(
            "After invalidation, no re-entry until new pivot low/high sequence forms with hold confirmation.",
            "FAILED_BREAK_RISK_OFF setup enforces no-add and no-immediate-reentry state until reset evidence appears.",
        ),
        traceability_fields=(
            "impulse_low_price",
            "impulse_high_price",
            "impulse_start_timestamp",
            "impulse_high_timestamp",
            "structure_timeframe",
            "break_hold_status",
            "failed_break_flag",
        ),
        calibration_notes="Structural promotion and failure-window settings are deterministic defaults pending replay validation.",
        notes="Structural impulse detection is fully explicit for P02 with break/hold and failed-break semantics.",
    ),
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
        zones=("COMPRESSION_ZONE", "BREAKOUT_ACCEPTANCE_ZONE", "RISK_OFF_REENTRY_BLOCK_ZONE"),
        notes="Structure doctrine supports continuation families and failed-break risk-off governance across PRE/RTH/AH.",
    ),
    position_management=PositionManagementV2(
        allow_scale_in=True,
        max_adds_per_position=2,
        allow_partials=True,
        averaging_down_allowed=False,
        notes=(
            "Scale-in only on renewed confirmation and positive excursion. No averaging down. Partials are mandatory on extension milestones."
        ),
    ),
    trailing_model=TrailingModelV2(
        rules=(
            TrailingRuleV2("TRAIL_TO_PIVOT", "After first extension and new higher-low", "Move stop to last valid pivot / reclaim anchor."),
            TrailingRuleV2("TRAIL_AFTER_PARTIAL", "After first partial", "Tighten stop to protect realized gains while preserving continuation room."),
            TrailingRuleV2("TRAIL_WEAKNESS", "Momentum weakness evidence escalates", "Tighten to intrabar invalidation and disallow new adds."),
        )
    ),
    exit_model=ExitModelV2(
        rules=(
            ExitRuleV2("X_HARD_INVALIDATION", "Structural invalidation level is breached", "Exit full position immediately."),
            ExitRuleV2("X_MOMENTUM_FAILURE", "Failed reclaim plus volume fade or failed-break signature", "Exit at least 50% and evaluate full flatten."),
            ExitRuleV2("X_TIME_STOP_1M", "No favorable progress within 6 one-minute bars after entry", "Flatten and recycle capital."),
            ExitRuleV2("X_TIME_STOP_5M", "No favorable progress within 3 five-minute bars for slower phase", "Flatten and recycle capital."),
            ExitRuleV2("X_PARTIAL_EXTENSION", "Price extends >=1R then >=2R", "Take systematic partials and tighten stop after each partial."),
        )
    ),
    safety_model=SafetyModelV2(
        rules=(
            SafetyRuleV2("S_HALT_GUARD", "halted=True or exchange halt/resumption state is unstable", "Block new entries and require 5-minute stability window post-resume."),
            SafetyRuleV2("S_DATA_DEGRADATION", "Missing/stale required candidate fields", "Pause entries for next 3 decision cycles and emit degradation artifact."),
            SafetyRuleV2("S_LOSS_STREAK_TIER1", "Two consecutive full-risk losses", "Reduce size tier by one step for next 5 qualified opportunities."),
            SafetyRuleV2("S_LOSS_STREAK_TIER2", "Three consecutive full-risk losses", "Pause new entries for remainder of session unless manual governance override."),
            SafetyRuleV2("S_SPREAD_SHOCK", "spread_pct exceeds spread_max_pct by >50%", "Immediate no-new-entry throttle; open positions managed risk-off only."),
        )
    ),
    stock_selection_law=StockSelectionLawV2(
        price_model=PriceModelV2(
            min_price=2.0,
            max_price=80.0,
            preferred_upper_bound=30.0,
            reject_sub_dollar_rule=True,
            rationale_commentary=(
                "P02 targets liquid intraday momentum where statistical continuation is observable; low-priced micro-noise and very high-priced low-rotation names are deprioritized."
            ),
            calibration_notes="Explicit governance defaults pending replay calibration.",
        ),
        gap_model=GapModelV2(
            hard_gap_threshold=2.0,
            soft_gap_threshold=0.8,
            percent_change_ranking_law=(
                "Percent change is a ranking contributor among eligible symbols; hard gap gate is intentionally modest to include non-gap continuation names."
            ),
            gap_vs_pct_change_distinction=(
                "Gap is an eligibility context variable; pct_change is a continuous ranking/priority variable throughout the session."
            ),
            calibration_notes="Explicit governance defaults pending replay calibration.",
        ),
        volume_model=VolumeModelV2(
            min_total_volume=800_000,
            min_premarket_volume=100_000,
            dollar_volume_min=6_000_000.0,
            liquidity_commentary=(
                "Liquidity law emphasizes executable turnover and session participation; premarket minimum ensures PRE readiness while not forcing catalyst dependence."
            ),
            calibration_notes="Explicit governance defaults pending replay calibration.",
        ),
        relative_volume_model=RelativeVolumeModelV2(
            rvol_minimum=1.8,
            calibration_commentary=(
                "RVOL is a primary law for P02 because continuation edge depends on participation persistence, not just absolute gap size."
            ),
            calibration_notes="Explicit governance defaults pending replay calibration.",
        ),
        float_model=FloatModelV2(
            float_max_millions=500.0,
            float_preferred_zone="20M-250M is preferred for tradability without requiring extreme low-float behavior.",
            float_explosive_zone="<20M is monitored as high-volatility subset, not primary law.",
            inverse_weighting_in_ranking=True,
            float_data_sources=("YAHOO", "FINVIZ", "NASDAQ"),
            ibkr_not_primary_reason="IBKR scanner feed is execution-first and not canonical for corporate float metadata quality.",
            cache_policy_commentary="Float cache updates daily premarket; stale float marks receive ranking penalty, not hard exclusion.",
            calibration_notes="Explicit governance defaults pending replay calibration.",
        ),
        catalyst_model=CatalystModelV2(
            require_catalyst=False,
            catalyst_quality_levels=("SEC_FILINGS", "EARNINGS", "GUIDANCE", "MACRO", "NEWSWIRE"),
            internal_news_engine_primary=True,
            rss_fast_list_support=True,
            liquidity_proxy_when_uncertain=True,
            commentary=(
                "Catalyst is optional for P02 statistical continuation: presence boosts confidence/ranking, but absence does not invalidate a liquid high-participation setup."
            ),
        ),
    ),
    liquidity_sanity_model=LiquiditySanityModelV2(
        spread_max_pct=0.60,
        halt_policy=(
            "If halted=True or resumption auction instability is detected, block entries; after resume require stabilization window and structure revalidation."
        ),
        ssr_handling=(
            "P02 baseline deployment is long-biased; SSR is tracked for telemetry and any short-side runtime extension must require separate governance enablement."
        ),
        execution_feasibility_commentary=(
            "Spread metric uses percentage units (spread_pct). Candidates violating spread cap are removed from entry eligibility regardless of rank."
        ),
        calibration_notes="Spread and feasibility thresholds are explicit defaults pending replay calibration.",
    ),
    ranking_model=RankingModelV2(
        weight_pct_change=0.22,
        weight_rvol=0.34,
        weight_float_inverse=0.14,
        weight_catalyst=0.08,
        liquidity_penalty=0.22,
        ranking_commentary=(
            "P02 ranking is participation-first: RVOL and liquidity-adjusted continuation quality dominate. "
            "Catalyst is a minor boost; ranking is not a Ross 5-pillar clone. Normalize each factor with deterministic clamping before weighted aggregation."
        ),
        calibration_notes="Weights are governance defaults pending replay optimization.",
    ),
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
            "short_interest_pct",
            "borrow_rate",
            "regime_tag",
            "updated_at",
        ),
        notes=(
            "Required fields align to canonical candidate adapter names. Mapping note: legacy aliases spread_bps->spread_pct, "
            "session_phase->session_label, halt_status->halted must be resolved upstream before policy evaluation."
        ),
    ),
    premarket_preparation=PremarketPreparationModelV2(
        required_levels=(
            PremarketLevelSpecV2("PM_HIGH", "Premarket high for continuation breakout context."),
            PremarketLevelSpecV2("PM_LOW", "Premarket low for invalidation anchoring."),
            PremarketLevelSpecV2("PRIOR_DAY_HIGH", "Prior-day high for extension/room-to-run checks."),
            PremarketLevelSpecV2("PRIOR_DAY_LOW", "Prior-day low for failure-risk context."),
        ),
        required_filters=(
            PremarketFilterSpecV2("LIQUIDITY", "Liquidity and dollar-volume minima must be satisfied."),
            PremarketFilterSpecV2("RVOL", "Relative volume minimum must be satisfied for continuation eligibility."),
            PremarketFilterSpecV2("EXECUTABILITY", "Spread and halt-state checks must be satisfied before handoff."),
        ),
        optional_filters=(
            PremarketFilterSpecV2("CATALYST", "Catalyst quality boosts rank but is not mandatory.", required=False),
            PremarketFilterSpecV2("FLOAT_CONTEXT", "Float context informs volatility sizing overlays.", required=False),
        ),
        room_to_run_policy=(
            "Require measurable room-to-run versus nearby resistance for continuation entries; blocked room may allow only risk-off or no-trade decisions."
        ),
        notes="Premarket process is explicit for PRE readiness and deterministic RTH handoff.",
    ),
    intrabar_execution=IntrabarExecutionModelV2(
        phase_specs=(
            IntrabarPhaseSpecV2(
                "OPENING_FAST",
                "Opening Fast",
                "High-volatility open; fastest monitoring and strict structure validation.",
                "Entries allowed only for opening and reclaim families with full confirmation stack.",
            ),
            IntrabarPhaseSpecV2(
                "MIDDAY_NORMAL",
                "Midday Normal",
                "Lower volatility; prioritize quality over frequency and enforce time-stops.",
                "Entries allowed for range expansion and pullback continuation only when participation confirms.",
            ),
            IntrabarPhaseSpecV2(
                "LATE_DAY_SLOW",
                "Late Day Slow",
                "Late-session liquidity transitions; prefer de-risking over new risk.",
                "New entries restricted; risk-off and exit controls remain fully active.",
            ),
        ),
        timeframe_map=(
            IntrabarTimeframeMapV2(
                "OPENING_FAST",
                ("15MIN", "5MIN", "1MIN"),
                ("5MIN", "1MIN"),
                ("10SEC", "1MIN"),
                "Intrabar can accelerate risk exits; entry validity still requires structure hold on 1MIN.",
            ),
            IntrabarTimeframeMapV2(
                "MIDDAY_NORMAL",
                ("15MIN", "5MIN", "1MIN"),
                ("5MIN", "1MIN"),
                ("1MIN",),
                "Candle-close confirmation preferred; intrabar override reserved for safety exits.",
            ),
            IntrabarTimeframeMapV2(
                "LATE_DAY_SLOW",
                ("15MIN", "5MIN"),
                ("5MIN",),
                ("1MIN",),
                "Late-day execution prioritizes exits/partials; new entries require exceptional confirmation.",
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
                "Evaluate on 1MIN cadence with 5MIN structure checkpoint; block over-trading during low-participation periods.",
            ),
            IntrabarCadenceRuleV2(
                "CADENCE_LATE",
                ("LATE_DAY_SLOW",),
                "Focus on risk reduction cadence; discontinue fresh setups near session close windows.",
            ),
        ),
        symbol_rotation_law=SymbolRotationLawV2(
            doctrine=(
                "Rotate focus toward symbols with sustained RVOL, valid structure hold, and stable spread_pct; "
                "deprioritize symbols that trigger failed-break risk-off or data degradation flags."
            ),
            prioritization_rules=(
                "Prioritize highest continuation-quality score after liquidity penalty.",
                "Do not rotate into symbols currently under halt/data/safety cooldown.",
                "Cap active focus to preserve deterministic execution quality.",
            ),
            rotation_triggers=(
                "Current focus symbol loses structure-hold confirmation.",
                "Spread or liquidity drifts outside executable thresholds.",
                "Alternative symbol's continuation score exceeds focus symbol by governance margin.",
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
            "OPENING_CONTINUATION and VWAP_RECLAIM_CONTINUATION are most active in OPENING_FAST; "
            "RANGE_EXPANSION_BREAKOUT and PULLBACK_CONTINUATION dominate MIDDAY_NORMAL; "
            "FAILED_BREAK_RISK_OFF is active in all phases as an override safety family."
        ),
        notes=(
            "Intrabar model is explicit and deterministic. Intrabar override authority is limited to risk-reduction (emergency exits/partials), "
            "not discretionary new entries."
        ),
    ),
    levels_and_zones=(
        "PM_HIGH",
        "PM_LOW",
        "OPENING_RANGE_HIGH",
        "OPENING_RANGE_LOW",
        "VWAP",
        "DAY_HIGH",
        "DAY_LOW",
        "PRIOR_DAY_HIGH",
        "PRIOR_DAY_LOW",
        "COMPRESSION_ZONE",
        "BREAKOUT_ACCEPTANCE_ZONE",
        "RISK_OFF_REENTRY_BLOCK_ZONE",
    ),
    notes=(
        "P02 StrategyPolicyV2 is fully explicit and audit-ready: all domains intentionally populated with deterministic defaults and "
        "calibration notes where governance tuning is pending."
    ),
)
