from src.strategy_policy_v2.policy_v2 import (
    ConfirmationSpecV2,
    DataRequirementsV2,
    ExecutionModelV2,
    ExitModelV2,
    ExitRuleV2,
    IntentContractV2,
    ModeSemanticsV2,
    PatternCatalogV2,
    PatternSpecV2,
    PremarketFilterSpecV2,
    PremarketLevelSpecV2,
    PremarketPreparationModelV2,
    PositionManagementV2,
    RiskModelV2,
    SafetyModelV2,
    SafetyRuleV2,
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
        )
    ),
    trigger_model=TriggerModelV2(
        entries=(
            TriggerEntrySpecV2("T_MICRO_RECLAIM", "BREAKOUT_RECLAIM", "Enter on first green candle breaking last red high after 2-3 red pullback bars.", ("OPENING_DRIVE", "MIDDAY", "LATE_DAY")),
            TriggerEntrySpecV2("T_PULLBACK_HIGH_BREAK", "PULLBACK_CONTINUATION", "Enter on pullback high reclaim or break of prior candle high.", ("RTH", "PRE")),
            TriggerEntrySpecV2("T_ORB_BREAK", "OPENING_RANGE_BREAK", "Enter on break above opening range high with hold.", ("RTH_OPEN",)),
            TriggerEntrySpecV2("T_KEY_LEVEL_BREAK", "LEVEL_BREAK", "Enter on break of PMH/HOD/flag high/whole-half dollar with momentum.", ("PRE", "RTH", "AH")),
            TriggerEntrySpecV2("T_RECLAIM", "VWAP_EMA_RECLAIM", "Enter on reclaim of VWAP/EMA9/EMA20 with continuation structure.", ("RTH", "AH")),
        ),
        confirmations=(
            ConfirmationSpecV2("C_VOLUME_EXPANSION", "Breakout volume should exceed pullback/consolidation volume."),
            ConfirmationSpecV2("C_MACD_POSITIVE", "MACD should be positive for entries when available."),
            ConfirmationSpecV2("C_HOLD_ABOVE_STRUCTURE", "Price must hold above VWAP/EMA9/EMA20 for long bias in pullbacks."),
            ConfirmationSpecV2("C_RVOL_IN_PLAY", "Relative volume and in-play gates must pass for candidate eligibility."),
            ConfirmationSpecV2("C_NO_TOPPING", "No topping-tail hard reversal signal on monitored structure timeframe."),
        ),
    ),
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
    data_requirements=DataRequirementsV2(
        required_fields=(
            "symbol",
            "session_label",
            "last_price",
            "pct_change",
            "volume",
            "rvol",
            "dollar_volume",
            "gate_checks",
            "candles_10s_1m_5m",
            "vwap",
            "ema9",
            "ema20",
            "premarket_high",
            "hod",
        ),
        optional_fields=(
            "bid",
            "ask",
            "spread_pct",
            "float_millions",
            "halted",
            "ssr",
            "macd",
            "l2_iceberg_signals",
            "news_catalyst",
        ),
        notes="If required fields are absent, policy mandates pause/reject semantics rather than speculative execution.",
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
            "validate room-to-run (incl EMA200), and only then proceed to intrabar execution (10SEC) during OPENING_DRIVE."
        ),
    ),
    notes=(
        "Spec-only full-law policy for P01 Ross Momentum. Gating is expected at scanner eligibility, "
        "pattern evaluation, and risk overlay stages; no runtime wiring changes are introduced here."
    ),
)
