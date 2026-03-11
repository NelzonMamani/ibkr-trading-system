from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from src.strategies.ross_momentum.strategy_policy import POLICY_V2


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


def test_stock_selection_law_has_all_five_pillars_structurally() -> None:
    law = POLICY_V2.stock_selection_law
    assert law.price_model is not None
    assert law.gap_model is not None
    assert law.volume_model is not None
    assert law.relative_volume_model is not None
    assert law.float_model is not None
    assert law.catalyst_model is not None


def test_float_and_catalyst_are_structural_and_not_optional() -> None:
    required = set(POLICY_V2.data_requirements.required_fields)
    optional = set(POLICY_V2.data_requirements.optional_fields)

    assert "float_millions" in required
    assert "float_millions" not in optional
    assert POLICY_V2.stock_selection_law.float_model.float_data_sources == ("YAHOO", "FINVIZ", "NASDAQ")
    assert POLICY_V2.stock_selection_law.catalyst_model.require_catalyst is True


def test_volume_and_rvol_are_separated_models() -> None:
    law = POLICY_V2.stock_selection_law
    assert law.volume_model.min_total_volume >= 1
    assert law.volume_model.min_premarket_volume >= 1
    assert law.relative_volume_model.rvol_minimum > 0


def test_stock_selection_doctrine_has_no_placeholders_or_todos() -> None:
    disallowed = ("placeholder", "todo")
    for component in (
        POLICY_V2.stock_selection_law,
        POLICY_V2.liquidity_sanity_model,
        POLICY_V2.ranking_model,
    ):
        for text in _iter_strings(component):
            lowered = text.lower()
            assert all(token not in lowered for token in disallowed), text
