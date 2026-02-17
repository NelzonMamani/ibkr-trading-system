from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Tuple

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
    notes: str = "Risk model is strategy-specific and spec-only in V2"


@dataclass(frozen=True)
class ExecutionModelV2:
    preferred_order_types: tuple[str, ...] = ("LIMIT",)
    allow_market_orders: bool = False
    allow_extended_hours: bool = True
    notes: str = "Execution constraints are declarative in V2"


@dataclass(frozen=True)
class IntentContractV2:
    emitted_intents: tuple[str, ...] = ("DECISION_INTENT",)
    emitted_artifacts: tuple[str, ...] = ("strategy_decision",)
    notes: str = "Spec-only intent contract"


@dataclass(frozen=True)
class SetupFamilySpecV2:
    setup_id: str
    name: str
    thesis: str
    timeframes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SetupFamiliesV2:
    families: tuple[SetupFamilySpecV2, ...] = ()


@dataclass(frozen=True)
class PatternSpecV2:
    pattern_id: str
    name: str
    pattern_type: Literal["SINGLE_CANDLE", "MULTI_CANDLE", "EXECUTION", "RISK"] = "EXECUTION"
    role: str = ""


@dataclass(frozen=True)
class PatternCatalogV2:
    patterns: tuple[PatternSpecV2, ...] = ()


@dataclass(frozen=True)
class TriggerEntrySpecV2:
    trigger_id: str
    entry_type: str
    condition: str
    time_windows: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfirmationSpecV2:
    confirmation_id: str
    condition: str
    required: bool = True


@dataclass(frozen=True)
class TriggerModelV2:
    entries: tuple[TriggerEntrySpecV2, ...] = ()
    confirmations: tuple[ConfirmationSpecV2, ...] = ()


@dataclass(frozen=True)
class StructureModelV2:
    levels: tuple[str, ...] = ()
    zones: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class PositionManagementV2:
    allow_scale_in: bool = False
    max_adds_per_position: int = 0
    allow_partials: bool = True
    averaging_down_allowed: bool = False
    notes: str = ""


@dataclass(frozen=True)
class TrailingRuleV2:
    trail_id: str
    condition: str
    stop_adjustment: str


@dataclass(frozen=True)
class TrailingModelV2:
    rules: tuple[TrailingRuleV2, ...] = ()


@dataclass(frozen=True)
class ExitRuleV2:
    exit_id: str
    condition: str
    action: str


@dataclass(frozen=True)
class ExitModelV2:
    rules: tuple[ExitRuleV2, ...] = ()


@dataclass(frozen=True)
class SafetyRuleV2:
    safety_id: str
    trigger: str
    behavior: str


@dataclass(frozen=True)
class SafetyModelV2:
    rules: tuple[SafetyRuleV2, ...] = ()


@dataclass(frozen=True)
class DataRequirementsV2:
    required_fields: Tuple[str, ...] = ()
    optional_fields: Tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class PremarketLevelSpecV2:
    level_id: str
    description: str


@dataclass(frozen=True)
class PremarketFilterSpecV2:
    filter_id: str
    description: str
    required: bool = True


@dataclass(frozen=True)
class PremarketPreparationModelV2:
    """
    Spec-only premarket due diligence model.
    Encodes what the trader checks BEFORE trading begins, and what must be true
    for a symbol to be considered 'tradable today' for this strategy.
    """

    scan_focus: Tuple[str, ...] = ("GAPPERS", "TOP_PCT_GAINERS", "RELATIVE_VOLUME", "CATALYST_NEWS")
    higher_timeframe_context: Tuple[str, ...] = ("DAILY", "WEEKLY")
    required_levels: Tuple[PremarketLevelSpecV2, ...] = ()
    required_filters: Tuple[PremarketFilterSpecV2, ...] = ()
    optional_filters: Tuple[PremarketFilterSpecV2, ...] = ()
    room_to_run_policy: str = ""
    notes: str = ""


@dataclass(frozen=True)
class IntrabarPhaseSpecV2:
    phase_id: str
    phase_name: str
    doctrine: str
    trading_intent_policy: str = ""


@dataclass(frozen=True)
class IntrabarTimeframeMapV2:
    phase_id: str
    analysis_timeframes: tuple[str, ...] = ()
    structure_timeframes: tuple[str, ...] = ()
    execution_timeframes: tuple[str, ...] = ()
    candle_close_policy: str = ""


@dataclass(frozen=True)
class IntrabarCadenceRuleV2:
    rule_id: str
    applies_to_phases: tuple[str, ...] = ()
    doctrine: str = ""


@dataclass(frozen=True)
class IntrabarSafetyThrottleV2:
    throttle_id: str
    trigger: str
    behavior: str


@dataclass(frozen=True)
class SymbolRotationLawV2:
    doctrine: str = ""
    prioritization_rules: tuple[str, ...] = ()
    rotation_triggers: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntrabarExecutionModelV2:
    phase_specs: tuple[IntrabarPhaseSpecV2, ...] = ()
    timeframe_map: tuple[IntrabarTimeframeMapV2, ...] = ()
    cadence_rules: tuple[IntrabarCadenceRuleV2, ...] = ()
    symbol_rotation_law: SymbolRotationLawV2 = field(default_factory=SymbolRotationLawV2)
    safety_throttles: tuple[IntrabarSafetyThrottleV2, ...] = ()
    setup_family_relationship: str = ""
    notes: str = ""


@dataclass(frozen=True)
class StrategyPolicyV2:
    identity: StrategyIdentityV2
    selection_plan: SelectionPlan
    mode_semantics: ModeSemanticsV2
    session_semantics: SessionSemanticsV2
    risk_model: RiskModelV2
    execution_model: ExecutionModelV2
    intent_contract: IntentContractV2
    setup_families: SetupFamiliesV2 = field(default_factory=SetupFamiliesV2)
    pattern_catalog: PatternCatalogV2 = field(default_factory=PatternCatalogV2)
    trigger_model: TriggerModelV2 = field(default_factory=TriggerModelV2)
    structure_model: StructureModelV2 = field(default_factory=StructureModelV2)
    position_management: PositionManagementV2 = field(default_factory=PositionManagementV2)
    trailing_model: TrailingModelV2 = field(default_factory=TrailingModelV2)
    exit_model: ExitModelV2 = field(default_factory=ExitModelV2)
    safety_model: SafetyModelV2 = field(default_factory=SafetyModelV2)
    data_requirements: DataRequirementsV2 = field(default_factory=DataRequirementsV2)
    premarket_preparation: PremarketPreparationModelV2 = field(default_factory=PremarketPreparationModelV2)
    intrabar_execution: IntrabarExecutionModelV2 = field(default_factory=IntrabarExecutionModelV2)
    levels_and_zones: tuple[str, ...] = ()
    notes: str = ""
