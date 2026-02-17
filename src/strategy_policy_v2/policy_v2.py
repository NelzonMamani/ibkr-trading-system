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
class CandleAndVolumeEvidenceModelV2:
    """Spec-only candle/volume evidence law; runtime wiring deferred."""

    evidence_tags: tuple[str, ...] = ()
    volume_bar_dominance_law: str = ""
    risk_exit_pause_semantics: str = ""


@dataclass(frozen=True)
class PullbackWeaknessTierModelV2:
    """Ross pullback-tier doctrine surface: 30/40/50 style weakness calibration."""

    ideal_pullback_max: float = 0.30
    caution_pullback_max: float = 0.40
    hard_warning_pullback_max: float = 0.50
    behavior_by_tier: tuple[str, ...] = (
        "<=30% retrace: strong continuation context when structure/volume confirm.",
        "30-40% retrace: normal pullback zone; continue with disciplined confirmation.",
        "40-50% retrace: caution tier; reduce aggression and tighten failure criteria.",
        ">=50% retrace: momentum thesis weakens; pause adds and prefer bail-out bias.",
    )
    intrabar_detection_notes: str = (
        "Weakness is evaluated on execution timeframes (e.g., 10SEC) and may trigger risk exits before a 1M candle close prints."
    )
    calibration_notes: str = "Subject to empirical validation; defaults encode Ross-style pullback doctrine."


@dataclass(frozen=True)
class VolumeDominanceProxyModelV2:
    """Proxy knobs for red/green volume-bar dominance; spec-only and calibration dependent."""

    enable_proxy_thresholds: bool = False
    red_vs_green_volume_pause_ratio: float = 1.0
    red_vs_impulse_green_volume_bail_ratio: float = 1.2
    commentary: str = (
        "Red/green volume-bar doctrine compares selling-pressure bars versus constructive impulse bars: "
        "if red volume begins to dominate the pullback/consolidation tape, continuation quality degrades and pause/bail bias increases. "
        "These ratios are proxy surfaces only and intentionally default to disabled to avoid false certainty."
    )
    calibration_notes: str = "Subject to empirical validation; ratio knobs are provisional doctrine proxies."


@dataclass(frozen=True)
class IntrabarExitOverrideLawV2:
    """Explicit authority for 10SEC-style intrabar exits before slower candle completion."""

    allowed_phases: tuple[str, ...] = ("OPENING_DRIVE", "MORNING_MOMENTUM")
    execution_timeframes: tuple[str, ...] = ("10SEC",)
    doctrine: str = (
        "Intrabar structure failure overrides candle-close confirmation: in fast phases, exit authority is immediate on 10SEC evidence "
        "to prevent hope-holding through failed breakouts."
    )
    override_examples: tuple[str, ...] = (
        "Breakout prints initial follow-through then rejects back below trigger structure.",
        "Pullback retrace expands beyond hard-warning tier and continuation quality collapses intrabar.",
        "Topping-tail/rejection bar appears while red volume dominance rises against the long thesis.",
        "Key support/reclaim level is lost intrabar before 1M close confirms.",
    )
    calibration_notes: str = "Subject to empirical validation; intrabar override scope should be validated with replay/statistics."


@dataclass(frozen=True)
class MomentumWeaknessAndExitLawV2:
    """Composite Ross weakness/exit doctrine joining pullback tiers, volume dominance, and intrabar override authority."""

    pullback_tiers: PullbackWeaknessTierModelV2 = field(default_factory=PullbackWeaknessTierModelV2)
    volume_dominance: VolumeDominanceProxyModelV2 = field(default_factory=VolumeDominanceProxyModelV2)
    intrabar_exit_override: IntrabarExitOverrideLawV2 = field(default_factory=IntrabarExitOverrideLawV2)
    candle_evidence_alignment_notes: str = (
        "Align weakness and exit decisions with CandleAndVolumeEvidenceModelV2 tags (e.g., DOJI indecision, SHOOTING_STAR rejection, "
        "HAMMER reclaim potential only with confirmation, and long topping tails as de-risk signals)."
    )
    notes: str = (
        "Spec-only doctrine surface: captures failure-fast 'breakout or bail out' behavior without wiring runtime evaluators. "
        "Gap/open behavior is evaluated at the open, while percent-change ranking remains primarily a preparation-stage sorting tool."
    )


@dataclass(frozen=True)
class ImpulseQualificationAndMeasurementLawV2:
    structural_impulse_definition: str = ""
    micro_impulse_definition: str = ""
    retracement_calculation_basis: str = ""
    entry_trigger_law: str = ""
    stop_placement_law: str = ""
    pullback_candle_structure_law: str = ""
    macd_preference_law: str = ""
    fifty_percent_reset_law: str = ""
    timeframe_alignment_notes: str = ""
    calibration_notes: str = ""
    notes: str = ""


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
class PriceModelV2:
    min_price: float = 1.0
    max_price: float = 20.0
    preferred_upper_bound: float = 10.0
    reject_sub_dollar_rule: bool = True
    rationale_commentary: str = ""
    calibration_notes: str = ""


@dataclass(frozen=True)
class GapModelV2:
    hard_gap_threshold: float = 10.0
    soft_gap_threshold: float = 7.0
    percent_change_ranking_law: str = ""
    gap_vs_pct_change_distinction: str = ""
    calibration_notes: str = ""


@dataclass(frozen=True)
class SessionReferenceLawV2:
    """Spec-only session reference law; runtime wiring deferred."""

    pct_change_reference: str = ""
    gap_reference: str = ""
    closed_session_preparation_notes: str = ""


@dataclass(frozen=True)
class VolumeModelV2:
    min_total_volume: int = 1_000_000
    min_premarket_volume: int = 100_000
    dollar_volume_min: float = 0.0
    liquidity_commentary: str = ""
    calibration_notes: str = ""


@dataclass(frozen=True)
class RelativeVolumeModelV2:
    rvol_minimum: float = 5.0
    calibration_commentary: str = ""
    calibration_notes: str = ""


@dataclass(frozen=True)
class FloatModelV2:
    float_max_millions: float = 20.0
    float_preferred_zone: str = ""
    float_explosive_zone: str = ""
    inverse_weighting_in_ranking: bool = True
    float_data_sources: tuple[str, ...] = ("YAHOO", "FINVIZ", "NASDAQ")
    ibkr_not_primary_reason: str = ""
    cache_policy_commentary: str = ""
    calibration_notes: str = ""


@dataclass(frozen=True)
class CatalystModelV2:
    require_catalyst: bool = True
    catalyst_quality_levels: tuple[str, ...] = ()
    internal_news_engine_primary: bool = True
    rss_fast_list_support: bool = True
    liquidity_proxy_when_uncertain: bool = True
    commentary: str = ""


@dataclass(frozen=True)
class StockSelectionLawV2:
    price_model: PriceModelV2 = field(default_factory=PriceModelV2)
    gap_model: GapModelV2 = field(default_factory=GapModelV2)
    volume_model: VolumeModelV2 = field(default_factory=VolumeModelV2)
    relative_volume_model: RelativeVolumeModelV2 = field(default_factory=RelativeVolumeModelV2)
    float_model: FloatModelV2 = field(default_factory=FloatModelV2)
    catalyst_model: CatalystModelV2 = field(default_factory=CatalystModelV2)


@dataclass(frozen=True)
class LiquiditySanityModelV2:
    spread_max_pct: float = 0.0
    halt_policy: str = ""
    ssr_handling: str = ""
    execution_feasibility_commentary: str = ""
    calibration_notes: str = ""


@dataclass(frozen=True)
class RankingModelV2:
    weight_pct_change: float = 0.0
    weight_rvol: float = 0.0
    weight_float_inverse: float = 0.0
    weight_catalyst: float = 0.0
    liquidity_penalty: float = 0.0
    ranking_commentary: str = ""
    calibration_notes: str = ""


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
    session_reference_law: SessionReferenceLawV2 = field(default_factory=SessionReferenceLawV2)
    candle_and_volume_evidence: CandleAndVolumeEvidenceModelV2 = field(default_factory=CandleAndVolumeEvidenceModelV2)
    momentum_weakness_and_exit: MomentumWeaknessAndExitLawV2 = field(default_factory=MomentumWeaknessAndExitLawV2)
    impulse_qualification: ImpulseQualificationAndMeasurementLawV2 = field(
        default_factory=ImpulseQualificationAndMeasurementLawV2
    )
    structure_model: StructureModelV2 = field(default_factory=StructureModelV2)
    position_management: PositionManagementV2 = field(default_factory=PositionManagementV2)
    trailing_model: TrailingModelV2 = field(default_factory=TrailingModelV2)
    exit_model: ExitModelV2 = field(default_factory=ExitModelV2)
    safety_model: SafetyModelV2 = field(default_factory=SafetyModelV2)
    stock_selection_law: StockSelectionLawV2 = field(default_factory=StockSelectionLawV2)
    liquidity_sanity_model: LiquiditySanityModelV2 = field(default_factory=LiquiditySanityModelV2)
    ranking_model: RankingModelV2 = field(default_factory=RankingModelV2)
    data_requirements: DataRequirementsV2 = field(default_factory=DataRequirementsV2)
    premarket_preparation: PremarketPreparationModelV2 = field(default_factory=PremarketPreparationModelV2)
    intrabar_execution: IntrabarExecutionModelV2 = field(default_factory=IntrabarExecutionModelV2)
    levels_and_zones: tuple[str, ...] = ()
    notes: str = ""
