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
    identity=StrategyIdentityV2(name="LONG_HORIZON_VALUE", strategy_id="P04"),
    selection_plan=PortfolioPlan(
        universe_source="FUNDAMENTAL_UNIVERSE",
        rebalance_frequency="MONTHLY",
        target_count=20,
    ),
    mode_semantics=ModeSemanticsV2(),
    session_semantics=SessionSemanticsV2(),
    risk_model=RiskModelV2(),
    execution_model=ExecutionModelV2(),
    intent_contract=IntentContractV2(),
    notes="Primary plan is PortfolioPlan; secondary fundamental screening can be represented via ScreenerPlan in a future union extension.",
)
