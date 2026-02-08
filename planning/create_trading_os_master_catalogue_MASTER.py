from pathlib import Path

ROOT = Path("TRADING_OS_MASTER_CATALOGUE")

def mkdir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def main():
    # ─────────────────────────────────────────────
    # ROOT
    # ─────────────────────────────────────────────
    mkdir(ROOT)

    # ─────────────────────────────────────────────
    # 00 — READ FIRST (GLOBAL GOVERNANCE)
    # ─────────────────────────────────────────────
    read_first = ROOT / "00_READ_FIRST"
    mkdir(read_first)

    # Files to be created later by Codex:
    # 00_READ_ORDER.md
    # 01_PROGRAM_RULES_LOCKED.md
    # 02_EPOCH_PROCESS_TEMPLATE.md
    # 03_GLOBAL_VERIFICATION_COMMANDS.md
    # 99_CODEX_MASTER_INSTRUCTION_BLOCK.md

    # ─────────────────────────────────────────────
    # 01 — CORE EPOCHS (ALL MUST BE CERTIFIED)
    # ─────────────────────────────────────────────
    core = ROOT / "01_CORE_EPOCHS"
    mkdir(core)

    core_epochs = [
        "E0_SYSTEM_LAW_AND_PURPOSE",
        "E1_TRACEABILITY_AND_OBSERVABILITY",
        "E2_POSITION_LIFECYCLE_ENGINE",
        "E3_RISK_ENGINE_COMPLETENESS",
        "E4_DATA_QUALITY_AND_MARKET_STATE",
        "E5_EXECUTION_ENGINE_AUTHORITY",
        "E6_SCANNER_STRATEGY_CONTRACT",
        "E7_MODE_PARITY_AND_SAFETY",
        "E8_REGIME_AND_MICROSTRUCTURE_LAYER",
        "E9_PERFORMANCE_ANALYTICS",
        "E10_CAPITAL_ALLOCATION",
        "E11_LEARNING_SYSTEM",
        "E12_RECOVERY_AND_HOUSEKEEPING",
        "E13_STRATEGY_FACTORY_STANDARD",
        "E14_DECISION_ARTIFACTS",
        "E15_FAILURE_MODES",
        "E16_NO_TRADE_CONTEXTS",
        "E17_STRATEGY_INTERACTION_RULES",
        "E18_STRATEGY_FOUNDATION_LAYER",
    ]

    for i, name in enumerate(core_epochs):
        epoch = core / f"{i:02d}_{name}"
        mkdir(epoch)

        # Standard per-epoch governance skeleton
        mkdir(epoch / "evidence")
        mkdir(epoch / "verification")

    # ─────────────────────────────────────────────
    # 02 — METADATA EPOCHS (SYSTEM SELF-KNOWLEDGE)
    # ─────────────────────────────────────────────
    meta = ROOT / "02_METADATA_EPOCHS"
    mkdir(meta)

    meta_epochs = [
        "M0_CANON_AND_SOURCES_OF_TRUTH",
        "M1_ARCHITECTURE_MAP",
        "M2_CONTRACT_REGISTRY",
        "M3_MODE_SEMANTICS_CERTIFICATION",
        "M4_TRACEABILITY_SEMANTICS",
        "M5_VERIFICATION_AUTHORITY",
        "M6_DATA_LIFECYCLE_GOVERNANCE",
        "M7_EPOCH_AUDIT_AND_CERTIFICATION",
        "M8_CHANGE_CONTROL",
        "M9_SIGNAL_SEMANTICS_REGISTRY",
        "M10_DATA_PROVENANCE_LEDGER",
    ]

    for i, name in enumerate(meta_epochs):
        epoch = meta / f"{i:02d}_{name}"
        mkdir(epoch)
        mkdir(epoch / "evidence")
        mkdir(epoch / "verification")

    # ─────────────────────────────────────────────
    # 03 — STRATEGY FOUNDATION (NON-EPOCH STRUCTURE)
    # ─────────────────────────────────────────────
    foundation = ROOT / "03_STRATEGY_FOUNDATION"
    mkdir(foundation)

    # 01 — Setup Families
    setups = foundation / "01_SETUP_FAMILIES"
    mkdir(setups)

    setup_families = [
        "SF_GAP_AND_GO",
        "SF_ORB",
        "SF_FIRST_PULLBACK_FIRST_FLAG",
        "SF_BULL_FLAG_TIGHT_FLAG",
        "SF_KEY_LEVEL_BREAK",
        "SF_ABCD_CONTINUATION",
        "SF_CUP_AND_HANDLE_INTRADAY",
        "SF_MOMENTUM_RECLAIM",
        "SF_VWAP_TREND_DAY",
        "SF_EMA_TREND_STAIRCASE",
        "SF_VOLATILITY_SQUEEZE",
        "SF_BOX_RANGE_BREAK",
        "SF_HOD_LOD_BREAK",
        "SF_FAILED_BREAKDOWN_REVERSAL",
        "SF_PDC_RECLAIM",
        "SF_POWER_HOUR_EXPANSION",
        "SF_HALT_RESUME",
        "SF_PARABOLIC_EXHAUSTION_AVOID",
    ]

    for i, name in enumerate(setup_families):
        mkdir(setups / f"{i:02d}_{name}")

    # 02 — Execution Triggers
    triggers = foundation / "02_EXECUTION_TRIGGERS"
    mkdir(triggers)

    execution_triggers = [
        "XL_MICRO_PULLBACK",
        "XL_ORB_BREAK",
        "XL_ORB_RETEST",
        "XL_FLAG_BREAK",
        "XL_FLAG_RECLAIM",
        "XL_VWAP_RECLAIM",
        "XL_EMA_RECLAIM",
        "XL_HOD_BREAK",
        "XL_RANGE_BREAK",
        "XL_ABCD",
        "XL_MEASURED_MOVE",
        "XL_LIQUIDITY_SWEEP_RECLAIM",
    ]

    for i, name in enumerate(execution_triggers):
        mkdir(triggers / f"{i:02d}_{name}")

    # 03 — Conditions
    conditions = foundation / "03_CONDITIONS"
    mkdir(conditions)

    condition_list = [
        "C_R2G_G2R",
        "C_TREND_ALIGNMENT",
        "C_VWAP_SIDE",
        "C_EMA_STACK",
        "C_REGIME_PERMISSION",
        "C_TIME_OF_DAY",
        "C_RELATIVE_VOLUME_STATE",
        "C_LIQUIDITY_STATE",
        "C_VOLATILITY_STATE",
    ]

    for i, name in enumerate(condition_list):
        mkdir(conditions / f"{i:02d}_{name}")

    # 04 — Confirmations
    confirmations = foundation / "04_CONFIRMATIONS"
    mkdir(confirmations)

    confirmation_list = [
        "K_VOLUME_CONFIRM",
        "K_RELATIVE_VOLUME_CONFIRM",
        "K_SPREAD_CONFIRM",
        "K_LIQUIDITY_CONFIRM",
        "K_LEVEL_HOLD",
        "K_BREAK_AND_HOLD",
        "K_RETEST_CONFIRM",
        "K_NO_PARABOLIC_EXHAUSTION",
        "K_DATA_QUALITY_CONFIRM",
    ]

    for i, name in enumerate(confirmation_list):
        mkdir(confirmations / f"{i:02d}_{name}")

    # 05 — Candlestick Patterns
    candles = foundation / "05_CANDLESTICK_PATTERNS"
    mkdir(candles)
    mkdir(candles / "01_SINGLE_CANDLE")
    mkdir(candles / "02_MULTI_CANDLE")

    # ─────────────────────────────────────────────
    # 04 — STRATEGIES
    # ─────────────────────────────────────────────
    strategies = ROOT / "04_STRATEGIES"
    mkdir(strategies)

    strategy_list = [
        "S_ROSS_MOMENTUM",
        "S_STATISTICAL_INTRADAY_MOMENTUM",
        "S_MEAN_REVERSION",
        "S_LONG_HORIZON_VALUE",
    ]

    for i, name in enumerate(strategy_list):
        mkdir(strategies / f"{i:02d}_{name}")

    # ─────────────────────────────────────────────
    # SYSTEM-LEVEL DOCUMENTS (AUTHORITATIVE)
    # ─────────────────────────────────────────────
    # These files live HERE and nowhere else:
    # SYSTEM_CONSTITUTION.md
    # SYSTEM_STATE.md
    # CODEX_GLOBAL_EXECUTION_INSTRUCTIONS.md

    print("✅ TRADING_OS_MASTER_CATALOGUE created and aligned with locked governance.")

if __name__ == "__main__":
    main()
