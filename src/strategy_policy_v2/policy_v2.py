from __future__ import annotations

from dataclasses import dataclass

from src.strategy_policy_v2.selection_plans import SelectionPlan


@dataclass(frozen=True)
class StrategyIdentityV2:
    name: str
    strategy_id: str
    version: str = "v2"


@dataclass(frozen=True)
class ModeSemanticsV2:
    sim_notes: str = "SIM supported"
    paper_notes: str = "PAPER supported"
    read_only_notes: str = "READ_ONLY emits no executable intents"
    live_notes: str = "LIVE requires separate runtime wiring; not in this PR"


@dataclass(frozen=True)
class SessionSemanticsV2:
    sessions: tuple[str, ...] = ("PRE", "RTH", "AH", "OVN")
    market_closed_semantics: str = "No trading intents when market is closed"


@dataclass(frozen=True)
class RiskModelV2:
    max_position_pct: float = 0.1
    daily_loss_limit: float = 0.02
    max_open_positions: int = 10
    notes: str = "Spec placeholder risk limits"


@dataclass(frozen=True)
class ExecutionModelV2:
    preferred_order_types: tuple[str, ...] = ("LIMIT",)
    allow_market_orders: bool = False
    allow_extended_hours: bool = True
    notes: str = "Spec placeholder execution constraints"


@dataclass(frozen=True)
class IntentContractV2:
    emitted_intents: tuple[str, ...] = ("DECISION_INTENT",)
    emitted_artifacts: tuple[str, ...] = ("strategy_decision",)
    notes: str = "Spec-only intent contract"


@dataclass(frozen=True)
class StrategyPolicyV2:
    identity: StrategyIdentityV2
    selection_plan: SelectionPlan
    mode_semantics: ModeSemanticsV2
    session_semantics: SessionSemanticsV2
    risk_model: RiskModelV2
    execution_model: ExecutionModelV2
    intent_contract: IntentContractV2
    setup_families: tuple[str, ...] = ()
    pattern_catalog: tuple[str, ...] = ()
    levels_and_zones: tuple[str, ...] = ()
    notes: str = ""
