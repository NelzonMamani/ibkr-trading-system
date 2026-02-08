from pathlib import Path

ROOT = Path("TRADING_OS_MASTER_CATALOGUE")

def mkdir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def main():
    # Root
    mkdir(ROOT)

    # 00 — READ FIRST
    mkdir(ROOT / "00_READ_FIRST")

    # 01 — CORE ARCH EPOCHS (P0 → P2 order)
    core_arch = ROOT / "01_CORE_ARCH_EPOCHS"
    mkdir(core_arch)

    core_epochs = [
        "E0_SYSTEM_LAW_TRUTH",
        "E1_TRACEABILITY_OBSERVABILITY",
        "E2_POSITION_LIFECYCLE_ENGINE",
        "E3_RISK_ENGINE_COMPLETENESS",
        "E4_DATA_QUALITY_MARKET_STATE",
        "E5_EXECUTION_ENGINE_AUTHORITY",
        "E6_SCANNER_STRATEGY_CONTRACT",
        "E7_MODE_PARITY",
        "E8_REGIME_LAYER",
        "E9_PERFORMANCE_ANALYTICS",
        "E10_CAPITAL_ALLOCATION",
        "E11_LEARNING_SYSTEM",
        "E12_RECOVERY_AND_HOUSEKEEPING",
        "E13_STRATEGY_FACTORY_STANDARD",
        "E14_DECISION_ARTIFACTS",
        "E15_FAILURE_MODES",
        "E16_NO_TRADE_CONTEXTS",
        "E17_STRATEGY_INTERACTION_RULES",
    ]

    for i, name in enumerate(core_epochs):
        mkdir(core_arch / f"{i:02d}_{name}")

    # 02 — METADATA EPOCHS
    meta = ROOT / "02_METADATA_EPOCHS"
    mkdir(meta)

    meta_epochs = [
        "M0_CANON",
        "M1_ARCHITECTURE_MAP",
        "M2_CONTRACT_REGISTRY",
        "M3_MODE_SEMANTICS_CERT",
        "M4_TRACEABILITY_SEMANTICS",
        "M5_VERIFICATION_AUTHORITY",
        "M6_DATA_LIFECYCLE_GOV",
        "M7_EPOCH_AUDIT_CERTIFICATION",
        "M8_CHANGE_CONTROL",
        "M9_SIGNAL_SEMANTICS_REGISTRY",
        "M10_DATA_PROVENANCE_LEDGER",
    ]

    for i, name in enumerate(meta_epochs):
        mkdir(meta / f"{i:02d}_{name}")

    # 03 — SETUP FAMILIES
    setups = ROOT / "03_SETUP_FAMILIES"
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

    # 04 — STRATEGIES
    strategies = ROOT / "04_STRATEGIES"
    mkdir(strategies)

    strategy_list = [
        "S_ROSS_MOMENTUM",
        "S_STATISTICAL_INTRADAY_MOMENTUM",
        "S_MEAN_REVERSION",
        "S_LONG_HORIZON_VALUE",
        "S_OPENING_DRIVE",
        "S_VWAP_RECLAIM",
        "S_POWER_HOUR",
        "S_VOL_EXPANSION",
    ]

    for i, name in enumerate(strategy_list):
        mkdir(strategies / f"{i:02d}_{name}")

    # 05 — EXECUTION TRIGGERS
    exec_triggers = ROOT / "05_EXECUTION_TRIGGERS"
    mkdir(exec_triggers)

    execution_logic = [
        "XL_MICRO_PULLBACK",
        "XL_FIRST_NEW_HIGH",
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
        "XL_OPENING_DRIVE_CONTINUATION",
    ]

    for i, name in enumerate(execution_logic):
        mkdir(exec_triggers / f"{i:02d}_{name}")

    # 06 — CONDITIONS (CONTEXT)
    conditions = ROOT / "06_CONDITIONS"
    mkdir(conditions)

    condition_list = [
        "C_R2G_G2R",
        "C_TREND_ALIGNMENT",
        "C_VWAP_SIDE",
        "C_EMA_STACK",
        "C_RANGE_EXPANSION",
        "C_RANGE_COMPRESSION",
        "C_OPENING_DRIVE_ACTIVE",
        "C_REGIME_PERMISSION",
        "C_TIME_OF_DAY",
        "C_RELATIVE_VOLUME_STATE",
        "C_LIQUIDITY_STATE",
        "C_VOLATILITY_STATE",
    ]

    for i, name in enumerate(condition_list):
        mkdir(conditions / f"{i:02d}_{name}")

    # 07 — CONFIRMATIONS
    confirmations = ROOT / "07_CONFIRMATIONS"
    mkdir(confirmations)

    confirmation_list = [
        "K_VOLUME_CONFIRM",
        "K_RELATIVE_VOLUME_CONFIRM",
        "K_SPREAD_CONFIRM",
        "K_LIQUIDITY_CONFIRM",
        "K_LEVEL_HOLD",
        "K_BREAK_AND_HOLD",
        "K_RETEST_CONFIRM",
        "K_NO_MAJOR_SELLER",
        "K_NO_PARABOLIC_EXHAUSTION",
        "K_DATA_QUALITY_CONFIRM",
    ]

    for i, name in enumerate(confirmation_list):
        mkdir(confirmations / f"{i:02d}_{name}")

    # 08 — DECISION ARTIFACTS
    decisions = ROOT / "08_DECISION_ARTIFACTS"
    mkdir(decisions)
    mkdir(decisions / "00_DA_DECISION_OBJECTS")

    # 09 — FAILURE MODES
    failures = ROOT / "09_FAILURE_MODES"
    mkdir(failures)
    mkdir(failures / "00_FM_FAILURE_TAXONOMY")

    # 10 — NO TRADE CONTEXTS
    no_trade = ROOT / "10_NO_TRADE_CONTEXTS"
    mkdir(no_trade)
    mkdir(no_trade / "00_NTC_NO_TRADE")

    # 11 — STRATEGY INTERACTION RULES
    interaction = ROOT / "11_STRATEGY_INTERACTION_RULES"
    mkdir(interaction)
    mkdir(interaction / "00_SIR_MULTI_STRATEGY_RULES")

    print("✅ TRADING_OS_MASTER_CATALOGUE created successfully.")

if __name__ == "__main__":
    main()
