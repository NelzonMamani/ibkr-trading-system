from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from src.strategies.ross_momentum.strategy_policy_v2 import POLICY_V2
from src.strategy_policy_v2.selection_plans import ScannerPlan


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
        return
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_strings(child)
        return
    if isinstance(value, (list, tuple, set)):
        for child in value:
            yield from _iter_strings(child)


def test_ross_policy_v2_core_sections_not_empty() -> None:
    assert isinstance(POLICY_V2.selection_plan, ScannerPlan)
    assert POLICY_V2.selection_plan.top_n > 0
    assert POLICY_V2.selection_plan.watchlist_limit_k > 0
    assert POLICY_V2.selection_plan.focus_limit_m > 0

    assert len(POLICY_V2.setup_families.families) >= 1
    assert len(POLICY_V2.pattern_catalog.patterns) >= 1
    assert len(POLICY_V2.trigger_model.entries) >= 1
    assert len(POLICY_V2.exit_model.rules) >= 1


def test_ross_policy_v2_session_and_intent_contract() -> None:
    sessions = set(POLICY_V2.session_semantics.sessions)
    assert "PRE" in sessions
    assert "RTH" in sessions

    emitted = set(POLICY_V2.intent_contract.emitted_intents)
    assert "DECISION_INTENT" in emitted


def test_ross_policy_v2_has_no_placeholders_or_todos() -> None:
    disallowed = ("placeholder", "todo")
    for text in _iter_strings(POLICY_V2):
        lowered = text.lower()
        assert all(token not in lowered for token in disallowed), text


def test_ross_policy_v2_session_reference_present_and_non_empty() -> None:
    model = POLICY_V2.session_reference_law
    assert model.pct_change_reference.strip()
    assert model.gap_reference.strip()
    assert model.closed_session_preparation_notes.strip()


def test_ross_policy_v2_candle_evidence_contains_required_tags() -> None:
    tags = {tag.upper() for tag in POLICY_V2.candle_and_volume_evidence.evidence_tags}
    assert "DOJI" in tags
    assert "SHOOTING_STAR" in tags
    assert "HAMMER" in tags


def test_ross_policy_v2_trigger_model_contains_required_new_trigger_ids() -> None:
    trigger_ids = {entry.trigger_id for entry in POLICY_V2.trigger_model.entries}
    assert "T_GAP_AND_GO_IMMEDIATE" in trigger_ids
    assert "T_STARTER_POSITION_ANTICIPATION" in trigger_ids
    assert "T_BREAKOUT_OR_BAILOUT" in trigger_ids
    assert "T_ORB_1M" in trigger_ids
    assert "T_ORB_5M" in trigger_ids


def test_ross_policy_v2_inventory_contains_new_sections() -> None:
    inventory = Path(
        "TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/P01_ROSS_MOMENTUM/ROSS_POLICY_V2_INVENTORY.md"
    ).read_text(encoding="utf-8")
    assert "Session Reference Law" in inventory
    assert "Candle/Volume Evidence Law" in inventory
    assert "Trigger/Entry Taxonomy Expansion" in inventory
    assert "Float Tier Doctrine" in inventory
    assert "Confirmation Layer (MACD + volume-bar rules)" in inventory
    assert "Momentum Weakness & Exit Law (Pullback tiers + intrabar exits + volume dominance proxies)" in inventory
    assert "Impulse Qualification & Measurement Law (Structural + Micro + 50% Reset Doctrine)" in inventory
    assert "Structural Impulse Detection Law (Pivot + Micro Promotion + Reset Doctrine)" in inventory



def test_p01_impulse_qualification_present_and_non_empty() -> None:
    law = POLICY_V2.impulse_qualification

    assert law.structural_impulse_definition.strip()
    assert law.micro_impulse_definition.strip()
    assert law.retracement_calculation_basis.strip()
    assert law.entry_trigger_law.strip()
    assert law.stop_placement_law.strip()
    assert law.pullback_candle_structure_law.strip()
    assert law.macd_preference_law.strip()
    assert law.fifty_percent_reset_law.strip()
    assert law.timeframe_alignment_notes.strip()
    assert law.calibration_notes.strip()
    assert law.notes.strip()

    assert "50%" in law.fifty_percent_reset_law
    assert "breaks the high of the previous red" in law.entry_trigger_law
    assert "pullback low" in law.stop_placement_law.lower()

    disallowed = ("placeholder", "todo")
    for text_value in law.__dict__.values():
        lowered = text_value.lower()
        assert all(token not in lowered for token in disallowed), text_value


def test_p01_structural_impulse_detection_model_present() -> None:
    model = POLICY_V2.structural_impulse_detection

    assert model.structure_timeframe_by_phase["OPENING_DRIVE"] == "1MIN"
    assert model.micro_timeframe_by_phase["OPENING_DRIVE"] == "10SEC"

    assert "50%" in " ".join(model.invalidation_rules)
    assert model.impulse_low_rule.strip()
    assert model.impulse_high_rule.strip()

    disallowed = ("placeholder", "todo")
    for value in model.__dict__.values():
        if isinstance(value, str):
            lowered = value.lower()
            assert all(token not in lowered for token in disallowed)
