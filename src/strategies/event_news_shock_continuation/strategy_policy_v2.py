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
    identity=StrategyIdentityV2(name="EVENT_NEWS_SHOCK_CONTINUATION", strategy_id="P12"),
    selection_plan=EventPlan(
        universe_source="EVENT_UNIVERSE",
        event_types=("EARNINGS", "NEWS", "GUIDANCE"),
        recency_window_minutes=240,
    ),
    mode_semantics=ModeSemanticsV2(),
    session_semantics=SessionSemanticsV2(),
    risk_model=RiskModelV2(),
    execution_model=ExecutionModelV2(),
    intent_contract=IntentContractV2(),
    notes="Event-driven selection plan (spec-only).",
)
