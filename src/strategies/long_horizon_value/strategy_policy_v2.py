from src.strategies.long_horizon_value.strategy_policy import (
    BASE_REQUIRED_MARGIN_OF_SAFETY,
    BUSINESS_QUALITY_REQUIREMENTS,
    ECONOMIC_ENGINE_REQUIREMENTS,
    FINANCIAL_STRENGTH_REQUIREMENTS,
    MARKET_CONFIDENCE_MULTIPLIER,
    MAX_NEW_ALLOCATION_PCT,
    MAX_SINGLE_POSITION_PCT,
    MAX_NET_DEBT_TO_EBITDA,
    MIN_INTEREST_COVERAGE,
    MIN_OPERATING_YEARS,
    MIN_OWNER_EARNINGS_POSITIVE_YEARS,
    required_margin_of_safety,
)
from src.strategy_policy_v2.policy_v2 import (
    ConfirmationSpecV2,
    DataRequirementsV2,
    ExecutionModelV2,
    ExitModelV2,
    ExitRuleV2,
    IntentContractV2,
    IntrabarCadenceRuleV2,
    IntrabarExecutionModelV2,
    IntrabarPhaseSpecV2,
    IntrabarSafetyThrottleV2,
    IntrabarTimeframeMapV2,
    LiquiditySanityModelV2,
    LongHorizonPortfolioConstraintsV2,
    LongHorizonRebalanceModelV2,
    LongHorizonThesisModelV2,
    LongHorizonValuationModelV2,
    ModeSemanticsV2,
    PatternCatalogV2,
    PatternSpecV2,
    PositionManagementV2,
    PremarketFilterSpecV2,
    PremarketLevelSpecV2,
    PremarketPreparationModelV2,
    RankingModelV2,
    RiskModelV2,
    SafetyModelV2,
    SafetyRuleV2,
    SessionReferenceLawV2,
    SessionSemanticsV2,
    SetupFamiliesV2,
    SetupFamilySpecV2,
    StrategyIdentityV2,
    StrategyPolicyV2,
    StructureModelV2,
    TrailingModelV2,
    TrailingRuleV2,
    TriggerEntrySpecV2,
    TriggerModelV2,
)
from src.strategy_policy_v2.selection_plans import PortfolioPlan


POLICY_V2 = StrategyPolicyV2(
    identity=StrategyIdentityV2(name="LONG_HORIZON_VALUE", strategy_id="P04"),
    selection_plan=PortfolioPlan(
        universe_source="FUNDAMENTAL_UNIVERSE",
        rebalance_frequency="MONTHLY",
        target_count=20,
    ),
    mode_semantics=ModeSemanticsV2(
        sim_notes="SIM executes the full thesis/quality/valuation stack and emits deterministic doctrine decisions.",
        paper_notes="PAPER mirrors SIM gates while producing broker-safe intents for long-horizon position management.",
        read_only_notes="READ_ONLY evaluates thesis and portfolio controls but blocks executable intents.",
        live_notes="LIVE requires runtime governance wiring and certifier approval for P04 doctrines.",
    ),
    session_semantics=SessionSemanticsV2(
        sessions=("PRE", "RTH", "AH", "OVN", "CLOSED"),
        market_closed_semantics="CLOSED permits thesis monitoring and risk-reducing actions only; no new entries.",
    ),
    risk_model=RiskModelV2(
        max_position_pct=MAX_SINGLE_POSITION_PCT,
        daily_loss_limit=0.05,
        max_open_positions=20,
        notes=(
            "Primary controls are thesis-break exits, valuation discipline, and portfolio drawdown governance; "
            "daily_loss_limit is secondary for long-horizon policy hygiene."
        ),
    ),
    execution_model=ExecutionModelV2(
        preferred_order_types=("LIMIT", "LIMIT_IF_TOUCHED"),
        allow_market_orders=False,
        allow_extended_hours=False,
        notes=(
            "Long-horizon execution doctrine: limit-first routing, size by ADV participation budget, "
            "avoid extended hours by default unless governance override is explicitly approved."
        ),
    ),
    intent_contract=IntentContractV2(
        emitted_intents=("DECISION_INTENT", "TRADE_INTENT", "RISK_DECISION", "REBALANCE_INTENT"),
        emitted_artifacts=("strategy_decision", "thesis_snapshot", "valuation_snapshot", "portfolio_constraints", "exit_decision"),
        notes="All emitted artifacts must carry trace_id and trigger/setup identifiers for deterministic auditability.",
    ),
    setup_families=SetupFamiliesV2(
        families=(
            SetupFamilySpecV2(
                "VALUE_DISCOUNT_ENTRY",
                "Value Discount Entry",
                "Initiate only when intrinsic value discount exceeds required margin of safety and thesis gates pass.",
                ("DAILY", "WEEKLY", "MONTHLY"),
            ),
            SetupFamilySpecV2(
                "QUALITY_COMPOUNDER_ACCUMULATION",
                "Quality Compounder Accumulation",
                "Add in valuation bands while business quality and financial strength remain intact.",
                ("DAILY", "WEEKLY", "MONTHLY"),
            ),
            SetupFamilySpecV2(
                "THESIS_MONITORING_HOLD",
                "Thesis Monitoring Hold",
                "Hold and monitor; rebalance only on scheduled review cadence unless thesis is invalidated.",
                ("DAILY", "WEEKLY", "MONTHLY", "QUARTERLY"),
            ),
            SetupFamilySpecV2(
                "THESIS_BREAK_RISK_OFF",
                "Thesis Break Risk-Off",
                "Hard de-risk when disconfirming fundamental evidence breaches canonical quality law.",
                ("DAILY", "WEEKLY", "MONTHLY"),
            ),
            SetupFamilySpecV2(
                "VALUATION_REALIZATION_TRIM",
                "Valuation Realization Trim",
                "Systematically trim as price migrates from fair value to overvaluation bands.",
                ("DAILY", "WEEKLY", "MONTHLY"),
            ),
        )
    ),
    pattern_catalog=PatternCatalogV2(
        patterns=(
            PatternSpecV2("PATTERN_INTRINSIC_DISCOUNT", "Intrinsic Discount Band", "EXECUTION", "Entry qualification from valuation model."),
            PatternSpecV2("PATTERN_THESIS_INTACT", "Thesis Intact Composite", "MULTI_CANDLE", "Business/financial/economic checklist continuity."),
            PatternSpecV2("PATTERN_THESIS_BREAK", "Thesis Break Composite", "RISK", "Hard-exit authority on disconfirming evidence."),
        )
    ),
    trigger_model=TriggerModelV2(
        entries=(
            TriggerEntrySpecV2(
                "T_MARGIN_OF_SAFETY_BUY",
                "VALUE_ENTRY",
                (
                    "Valuation discount >= required_margin_of_safety(market_confidence) and all required "
                    "quality/financial/economic confirmations pass."
                ),
                ("RTH",),
            ),
            TriggerEntrySpecV2(
                "T_ADD_ON_DIP",
                "ACCUMULATION_ADD",
                (
                    "Thesis intact and price enters approved valuation accumulation band; "
                    f"size per action <= {MAX_NEW_ALLOCATION_PCT:.2f}."
                ),
                ("RTH",),
            ),
            TriggerEntrySpecV2("T_REBALANCE_REVIEW", "REBALANCE", "Monthly review and rebalance cadence trigger.", ("CLOSED", "RTH")),
            TriggerEntrySpecV2("T_THESIS_BREAK_EXIT", "RISK_OFF_EXIT", "Disconfirming signals breach canonical thesis law; hard exit.", ("RTH", "CLOSED")),
            TriggerEntrySpecV2("T_OVERVALUATION_TRIM", "VALUATION_TRIM", "Valuation exceeds trim band; perform systematic trim.", ("RTH", "CLOSED")),
        ),
        confirmations=(
            ConfirmationSpecV2("C_DATA_QUALITY", "Required fundamentals and liquidity fields are fresh, complete, and internally consistent."),
            ConfirmationSpecV2("C_BUSINESS_QUALITY_UNDERSTANDABLE", "UNDERSTANDABLE_BUSINESS requirement is satisfied."),
            ConfirmationSpecV2("C_BUSINESS_QUALITY_DEMAND", "DURABLE_DEMAND requirement is satisfied."),
            ConfirmationSpecV2("C_BUSINESS_QUALITY_MOAT", "ECONOMIC_MOAT_PRESENT requirement is satisfied."),
            ConfirmationSpecV2("C_BUSINESS_QUALITY_MANAGEMENT", "RATIONAL_MANAGEMENT requirement is satisfied."),
            ConfirmationSpecV2("C_FINANCIAL_OPERATING_YEARS", f"Operating history >= {MIN_OPERATING_YEARS} years."),
            ConfirmationSpecV2("C_FINANCIAL_INTEREST_COVERAGE", f"Interest coverage >= {MIN_INTEREST_COVERAGE:.1f}."),
            ConfirmationSpecV2("C_FINANCIAL_LEVERAGE", f"Net debt / EBITDA <= {MAX_NET_DEBT_TO_EBITDA:.1f}."),
            ConfirmationSpecV2(
                "C_FINANCIAL_OWNER_EARNINGS_STABILITY",
                f"Positive owner earnings years >= {MIN_OWNER_EARNINGS_POSITIVE_YEARS}.",
            ),
            ConfirmationSpecV2("C_ECONOMIC_ENGINE_ESTIMABLE", "OWNERS_EARNINGS_ESTIMABLE requirement is satisfied."),
            ConfirmationSpecV2("C_ECONOMIC_ENGINE_FCF", "POSITIVE_FREE_CASH_FLOW requirement is satisfied."),
            ConfirmationSpecV2("C_ECONOMIC_ENGINE_REINVESTMENT", "REASONABLE_REINVESTMENT requirement is satisfied."),
            ConfirmationSpecV2(
                "C_MARGIN_OF_SAFETY",
                (
                    f"Discount to fair value meets dynamic threshold from required_margin_of_safety(); base={BASE_REQUIRED_MARGIN_OF_SAFETY:.2f}, "
                    f"multipliers={MARKET_CONFIDENCE_MULTIPLIER}."
                ),
            ),
            ConfirmationSpecV2("C_OPTIONAL_TAPE_CONTEXT", "Tape/volume context may refine timing but never veto a qualified fundamental entry.", required=False),
        ),
    ),
    session_reference_law=SessionReferenceLawV2(
        pct_change_reference="Percent-change is informational only; valuation and thesis dominate execution authority.",
        gap_reference="Gaps are treated as execution context, not as setup authority.",
        closed_session_preparation_notes="Closed-session workflow performs thesis monitoring, valuation refresh, and rebalance planning.",
    ),
    structure_model=StructureModelV2(
        levels=("FAIR_VALUE", "DISCOUNT_BAND", "ADD_BAND", "TRIM_BAND", "THESIS_BREAK_LEVEL"),
        zones=("MARGIN_OF_SAFETY_ZONE", "FAIR_VALUE_ZONE", "OVERVALUATION_ZONE"),
        notes="Structure is valuation-centric rather than intraday price-action-centric for P04.",
    ),
    position_management=PositionManagementV2(
        allow_scale_in=True,
        max_adds_per_position=4,
        allow_partials=True,
        averaging_down_allowed=False,
        notes=(
            "Adds allowed only inside predefined valuation bands with thesis intact; "
            f"single add allocation capped at {MAX_NEW_ALLOCATION_PCT:.2f}."
        ),
    ),
    trailing_model=TrailingModelV2(
        rules=(
            TrailingRuleV2("TRAIL_THESIS", "Thesis remains intact but risk concentration rises", "Trim to policy allocation bands."),
        )
    ),
    exit_model=ExitModelV2(
        rules=(
            ExitRuleV2("THESIS_BREAK_HARD_EXIT", "Any canonical disconfirming thesis signal is confirmed", "Exit full position immediately"),
            ExitRuleV2("VALUATION_REALIZATION_TRIM", "Price enters overvaluation trim bands", "Trim systematically per valuation doctrine"),
            ExitRuleV2("FUNDAMENTAL_DETERIORATION_EXIT", "Financial strength or economic engine gate fails on refresh", "Exit or step-down risk according to deterioration severity"),
        )
    ),
    safety_model=SafetyModelV2(
        rules=(
            SafetyRuleV2("D10_PAUSE", "Transient data latency/degradation with active positions", "PAUSE new entries; allow risk-reducing position management"),
            SafetyRuleV2("D10_REJECT", "Minimum fundamental entry field set is missing", "REJECT symbol for new entries deterministically"),
            SafetyRuleV2("D10_ABORT", "Corrupt or contradictory core accounting dataset", "ABORT rebalance/entry cycle and escalate"),
            SafetyRuleV2("D10_DEGRADE", "Optional context or non-critical fields are missing", "DEGRADE to management-only mode for existing positions"),
        )
    ),
    liquidity_sanity_model=LiquiditySanityModelV2(
        spread_max_pct=1.25,
        halt_policy="If halted or auction-unstable, block new entries; manage exits and de-risk only.",
        ssr_handling="SSR is contextual only; no short-side thesis exists for P04.",
        execution_feasibility_commentary="Orders must respect ADV participation and avoid forced liquidity-taking.",
        calibration_notes="Liquidity thresholds are conservative defaults for long-horizon position construction.",
    ),
    ranking_model=RankingModelV2(
        weight_pct_change=0.05,
        weight_rvol=0.05,
        weight_float_inverse=0.0,
        weight_catalyst=0.10,
        liquidity_penalty=0.20,
        ranking_commentary="Ranking is dominated by quality and valuation stack; tape/flow factors are secondary context.",
        calibration_notes="Weights intentionally de-emphasize short-term momentum for Buffett-style doctrine.",
    ),
    data_requirements=DataRequirementsV2(
        required_fields=(
            "symbol",
            "last_price",
            "market_confidence",
            "operating_years",
            "interest_coverage",
            "net_debt_to_ebitda",
            "owner_earnings_positive_years",
            "fair_value_estimate",
            "valuation_discount_pct",
            "free_cash_flow_positive",
            "avg_daily_dollar_volume",
            "spread_bps",
            "halt_status",
        ),
        optional_fields=(
            "management_quality_score",
            "moat_score",
            "segment_concentration",
            "insider_activity",
            "analyst_dispersion",
            "volume",
            "rvol",
        ),
        notes=(
            "D10 doctrine (deterministic): PAUSE on transient latency, REJECT new entries when required fundamental minimum set is missing, "
            "ABORT cycle on contradictory core statements, DEGRADE to manage-existing-positions-only when optional context degrades. "
            "Entry authority is blocked without required fundamentals; degradation never authorizes a new entry."
        ),
    ),
    long_horizon_thesis=LongHorizonThesisModelV2(
        business_quality_requirements=tuple(BUSINESS_QUALITY_REQUIREMENTS),
        financial_strength_requirements=tuple(FINANCIAL_STRENGTH_REQUIREMENTS),
        economic_engine_requirements=tuple(ECONOMIC_ENGINE_REQUIREMENTS),
        monitoring_cadence="MONTHLY",
        disconfirming_signals=(
            "Economic moat erosion or demand decay confirmed across reporting periods.",
            "Interest coverage breach or leverage drift above policy maximum.",
            "Owner earnings reliability breakdown or persistent negative free cash flow.",
            "Capital allocation behavior becomes inconsistent with rational management doctrine.",
        ),
        notes="Canonical Buffett-law thesis nucleus: checklist gates must remain true through the full holding lifecycle.",
    ),
    long_horizon_valuation=LongHorizonValuationModelV2(
        base_required_margin_of_safety=BASE_REQUIRED_MARGIN_OF_SAFETY,
        market_confidence_multiplier=MARKET_CONFIDENCE_MULTIPLIER,
        valuation_methods=("OWNER_EARNINGS_DISCOUNT", "NORMALIZED_FCF_MULTIPLE", "CONSERVATIVE_SUM_OF_PARTS"),
        margin_of_safety_bands=(
            f"HIGH confidence: discount >= {required_margin_of_safety('HIGH'):.2f}",
            f"MEDIUM confidence: discount >= {required_margin_of_safety('MEDIUM'):.2f}",
            f"LOW confidence: discount >= {required_margin_of_safety('LOW'):.2f}",
        ),
        fair_value_band_notes="Fair value zone: hold/rebalance without forced action unless portfolio constraints require trims.",
        trim_bands=(
            "Initial trim: valuation reaches fair value + 10% premium.",
            "Systematic trim: valuation reaches fair value + 20% premium.",
            "Aggressive trim / exit consideration: valuation reaches fair value + 35% premium with slowing quality momentum.",
        ),
        notes="Valuation discipline is deterministic and anchored to required_margin_of_safety(market_confidence).",
    ),
    long_horizon_rebalance=LongHorizonRebalanceModelV2(
        review_cadence="MONTHLY",
        fundamentals_refresh_cadence="QUARTERLY",
        turnover_cap_per_review=0.15,
        min_holding_period_days=180,
        notes="Rebalances are cadence-driven unless thesis-break doctrine escalates immediate risk-off action.",
    ),
    long_horizon_portfolio_constraints=LongHorizonPortfolioConstraintsV2(
        max_single_position_pct=MAX_SINGLE_POSITION_PCT,
        max_new_allocation_pct=MAX_NEW_ALLOCATION_PCT,
        sector_caps=(
            "Single sector exposure cap: 30% of portfolio market value.",
            "Top-2 sectors combined cap: 50% of portfolio market value.",
        ),
        cash_buffer_rule="Maintain 5-10% cash buffer for opportunistic adds and deterministic risk containment.",
        notes="Portfolio concentration, sector exposure, and add sizing are explicit hard constraints.",
    ),
    premarket_preparation=PremarketPreparationModelV2(
        required_levels=(
            PremarketLevelSpecV2("FAIR_VALUE", "Latest approved intrinsic fair value anchor."),
            PremarketLevelSpecV2("MARGIN_OF_SAFETY_BUY", "Required margin-of-safety buy threshold."),
        ),
        required_filters=(
            PremarketFilterSpecV2("THESIS_INTACT", "All canonical thesis checklist requirements remain valid."),
            PremarketFilterSpecV2("LIQUIDITY_EXECUTABLE", "Liquidity permits disciplined limit-first execution."),
        ),
        optional_filters=(
            PremarketFilterSpecV2("TAPE_CONTEXT", "Tape/volume context can improve timing but is non-binding.", required=False),
        ),
        room_to_run_policy="Room-to-run is measured as discount-to-fair-value gap rather than intraday structure expansion.",
        notes="Preparation emphasizes fundamentals refresh integrity and valuation-band readiness.",
    ),
    intrabar_execution=IntrabarExecutionModelV2(
        phase_specs=(
            IntrabarPhaseSpecV2("LONG_HORIZON", "Long-Horizon Execution", "NOT_APPLICABLE", "Intrabar signals never override thesis/valuation doctrine."),
        ),
        timeframe_map=(
            IntrabarTimeframeMapV2(
                "LONG_HORIZON",
                ("DAILY", "WEEKLY", "MONTHLY"),
                ("DAILY", "WEEKLY", "MONTHLY"),
                ("1MIN", "5MIN"),
                "Execution timing is tactical only; doctrine authority remains on long-horizon frames.",
            ),
        ),
        cadence_rules=(
            IntrabarCadenceRuleV2("CADENCE_MONTHLY_REVIEW", ("LONG_HORIZON",), "Execution cadence follows monthly rebalance doctrine and quarterly fundamental refresh."),
        ),
        safety_throttles=(
            IntrabarSafetyThrottleV2("THROTTLE_EVENT_RISK", "Material unscheduled event", "Pause adds until thesis impact is reviewed."),
        ),
        setup_family_relationship="Execution semantics are subordinate to value/thesis setup families and deterministic risk-off rules.",
        notes="Intrabar doctrine is context-only for P04; no intraday continuation authority.",
    ),
    notes="P04 canonical policy rebuilt to long-horizon Buffett-law nucleus with deterministic D10, valuation, and portfolio governance.",
)
