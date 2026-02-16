from src.strategy_policy_v2.policy_v2 import (
    ExecutionModelV2,
    IntentContractV2,
    ModeSemanticsV2,
    RiskModelV2,
    SessionSemanticsV2,
    StrategyIdentityV2,
    StrategyPolicyV2,
)
from src.strategy_policy_v2.selection_plans import EventPlan, PortfolioPlan, ScannerPlan


POLICY_V2 = StrategyPolicyV2(
    identity=StrategyIdentityV2(name="VOLATILITY_EXPANSION", strategy_id="P08"),
    selection_plan=ScannerPlan(
        universe_source="IBKR_TOP_GAINERS",
        ibkr_scan_code="TOP_PERC_GAIN",
        top_n=50,
        watchlist_limit_k=15,
        focus_limit_m=5,
        policy_name="VOLATILITY_EXPANSION",
        gating_profile="VOLATILITY_EXPANSION",
        session_allowlist=("PRE", "RTH"),
    ),
    mode_semantics=ModeSemanticsV2(),
    session_semantics=SessionSemanticsV2(),
    risk_model=RiskModelV2(),
    execution_model=ExecutionModelV2(),
    intent_contract=IntentContractV2(),
    notes="Scanner-driven selection plan (spec-only).",
)
