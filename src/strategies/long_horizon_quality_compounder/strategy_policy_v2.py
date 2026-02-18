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
    identity=StrategyIdentityV2(name="LONG_HORIZON_QUALITY_COMPOUNDER", strategy_id="P19"),
    selection_plan=PortfolioPlan(
        universe_source="FUNDAMENTAL_UNIVERSE",
        rebalance_frequency="MONTHLY",
        target_count=20,
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
        notes="D9 risk governance: hard per-position cap, daily stop, and escalation after consecutive invalidations.",
    ),
    execution_model=ExecutionModelV2(
        preferred_order_types=("LIMIT", "STOP_LIMIT"),
        allow_market_orders=False,
        allow_extended_hours=True,
        notes="D6 trigger execution doctrine is explicit and traceable with slippage-aware controls.",
    ),
    intent_contract=IntentContractV2(
        emitted_intents=("DECISION_INTENT", "TRADE_INTENT", "RISK_DECISION"),
        emitted_artifacts=("strategy_decision", "setup_evaluation", "risk_snapshot", "exit_decision"),
        notes="D13 monitoring: trace_id and setup_family_id are mandatory in every emitted artifact.",
    ),
    setup_families=SetupFamiliesV2(
        families=(
            SetupFamilySpecV2("PRIMARY_CONTINUATION", "Primary Continuation", "D1 thesis continuation after structural confirmation.", ("DAILY", "15MIN", "5MIN", "1MIN")),
            SetupFamilySpecV2("RECLAIM_OR_REVERSION", "Reclaim / Reversion", "Dislocation then re-acceptance with confirmation stack.", ("15MIN", "5MIN", "1MIN")),
            SetupFamilySpecV2("VOLATILITY_RESOLUTION", "Volatility Resolution", "Compression/expansion resolution under liquidity and risk gates.", ("5MIN", "1MIN")),
        )
    ),
    pattern_catalog=PatternCatalogV2(
        patterns=(
            PatternSpecV2("PATTERN_BREAKOUT", "Breakout Expansion", "EXECUTION", "Continuation trigger quality"),
            PatternSpecV2("PATTERN_RECLAIM", "Reclaim Hold", "MULTI_CANDLE", "Re-acceptance confirmation"),
            PatternSpecV2("PATTERN_FAILURE", "Failed Break", "RISK", "Bailout and de-risk authority"),
        )
    ),
    trigger_model=TriggerModelV2(
        entries=(
            TriggerEntrySpecV2("BREAK_AND_HOLD", "BREAKOUT", "Break and hold above decision level.", ("PRE", "RTH")),
            TriggerEntrySpecV2("RECLAIM_CONFIRM", "RECLAIM", "Reclaim anchor with participation.", ("RTH", "AH")),
            TriggerEntrySpecV2("PULLBACK_CONTINUATION", "PULLBACK", "Controlled pullback resumes thesis direction.", ("RTH",)),
        ),
        confirmations=(
            ConfirmationSpecV2("C_DATA_QUALITY", "Data quality is fresh and complete for decision authority."),
            ConfirmationSpecV2("C_LEVEL_BEHAVIOR", "Level break/retest behavior is stable and not immediately rejected."),
            ConfirmationSpecV2("C_LIQUIDITY", "Liquidity and spread remain executable for intended size."),
            ConfirmationSpecV2("C_VOLUME", "Volume/RVOL confirms participation in the thesis direction."),
        ),
    ),
    session_reference_law=SessionReferenceLawV2(
        pct_change_reference="Percent-change references prior close for cross-session continuity.",
        gap_reference="Gap references session open versus prior close for opening context only.",
        closed_session_preparation_notes="Closed-session preparation updates selection and risk tiers before next open.",
    ),
    structure_model=StructureModelV2(
        levels=("PM_HIGH", "PM_LOW", "VWAP", "DAY_HIGH", "DAY_LOW"),
        zones=("VALUE_AREA", "OPENING_RANGE", "IMBALANCE_ZONE"),
        notes="D3/D4 structure authority for level interaction and confirmation behavior.",
    ),
    position_management=PositionManagementV2(
        allow_scale_in=True,
        max_adds_per_position=2,
        allow_partials=True,
        averaging_down_allowed=False,
        notes="D8 scaling doctrine: add only with cushion and renewed confirmation; no averaging down.",
    ),
    trailing_model=TrailingModelV2(
        rules=(
            TrailingRuleV2("TRAIL_STRUCTURE", "New higher-low / lower-high prints", "Trail stop to invalidation structure."),
        )
    ),
    exit_model=ExitModelV2(
        rules=(
            ExitRuleV2("HARD_INVALIDATION", "Invalidation level breached", "Exit full position immediately"),
            ExitRuleV2("MOMENTUM_FAILURE", "Continuation fails back into range", "De-risk at least 50%"),
            ExitRuleV2("TARGET_SCALE", "R-multiple target reached", "Take systematic partial"),
            ExitRuleV2("TIME_STOP", "No progress in expected window", "Flatten and recycle capital"),
        )
    ),
    safety_model=SafetyModelV2(
        rules=(
            SafetyRuleV2("HALT_GUARD", "Volatility halt or regulatory pause", "Block new orders until tradability recertified"),
            SafetyRuleV2("DATA_DEGRADATION", "Delayed or missing core feed fields", "Pause entries and reject stale signals"),
            SafetyRuleV2("LOSS_STREAK", "Two consecutive full-risk losses", "Escalate and reduce size tier"),
            SafetyRuleV2("MODEL_DISAGREEMENT", "Setup family and regime gates disagree", "Mandatory no-trade decision"),
        )
    ),
    liquidity_sanity_model=LiquiditySanityModelV2(
        spread_max_pct=0.8,
        halt_policy="If halted or reopening auction is unstable, reject entries until stability checks pass.",
        ssr_handling="On SSR pressure, short-side actions are blocked and long-side size is reduced.",
        execution_feasibility_commentary="Execution feasibility must pass before trigger-to-order transition.",
        calibration_notes="Thresholds are governance defaults pending replay calibration.",
    ),
    ranking_model=RankingModelV2(
        weight_pct_change=0.35,
        weight_rvol=0.25,
        weight_float_inverse=0.20,
        weight_catalyst=0.20,
        liquidity_penalty=0.15,
        ranking_commentary="D2 universe ranking uses momentum, participation, structure, and liquidity penalties.",
        calibration_notes="Weights are policy defaults and must be empirically reviewed.",
    ),
    data_requirements=DataRequirementsV2(
        required_fields=("symbol", "last_price", "pct_change", "volume", "rvol", "spread_bps", "session_phase", "halt_status"),
        optional_fields=("news_catalyst", "float_shares", "short_interest_pct", "borrow_rate", "regime_tag"),
        notes="D10 governance: if required fields degrade, pause decisioning and reject entries until restored.",
    ),
    premarket_preparation=PremarketPreparationModelV2(
        required_levels=(
            PremarketLevelSpecV2("PM_HIGH", "Premarket high for breakout context."),
            PremarketLevelSpecV2("PM_LOW", "Premarket low for invalidation anchoring."),
        ),
        required_filters=(
            PremarketFilterSpecV2("LIQUIDITY", "Liquidity threshold must be satisfied."),
            PremarketFilterSpecV2("EXECUTABILITY", "Spread and tape quality must be executable."),
        ),
        optional_filters=(PremarketFilterSpecV2("CATALYST", "Catalyst confidence improves ranking priority.", required=False),),
        room_to_run_policy="D2 universe law requires room-to-run relative to nearby structure.",
        notes="D3 conditions and D4 confirmations are preflighted before session handoff.",
    ),
    intrabar_execution=IntrabarExecutionModelV2(
        phase_specs=(
            IntrabarPhaseSpecV2("INTRABAR_POLICY", "Intrabar Doctrine", "NOT_APPLICABLE", "Intrabar controls are explicitly declared."),
        ),
        timeframe_map=(
            IntrabarTimeframeMapV2(
                "INTRABAR_POLICY",
                ("5MIN", "1MIN"),
                ("5MIN", "1MIN"),
                ("10SEC", "1MIN") if "NOT_APPLICABLE" == "APPLICABLE" else ("1MIN", "5MIN"),
                "Intrabar exits may override candle close." if "NOT_APPLICABLE" == "APPLICABLE" else "NOT_APPLICABLE for intrabar override; candle-close authority only.",
            ),
        ),
        cadence_rules=(IntrabarCadenceRuleV2("CADENCE_CONTROL", ("INTRABAR_POLICY",), "Cadence adapts to liquidity and volatility regime."),),
        safety_throttles=(IntrabarSafetyThrottleV2("THROTTLE_NEWS", "Unscheduled news shock", "Throttle entries for cooling interval."),),
        setup_family_relationship="D12 authority is explicitly bound to setup family execution semantics.",
        notes="D14 constraints: implicit defaults are prohibited; every executable behavior is declared.",
    ),
    notes="Institutional Matrix V2 declaration includes D0 through D14 with explicit governance sections.",
)
