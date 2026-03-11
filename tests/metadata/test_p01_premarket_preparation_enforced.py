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


def test_premarket_preparation_present_and_nontrivial() -> None:
    model = POLICY_V2.premarket_preparation

    assert model is not None
    assert any(level.level_id == "L_EMA200_DAILY" for level in model.required_levels)

    required_filter_ids = {flt.filter_id for flt in model.required_filters}
    assert "F_ROOM_TO_RUN_HTF" in required_filter_ids
    assert "F_CATALYST_REQUIRED" in required_filter_ids

    scan_focus = set(model.scan_focus)
    assert "GAPPERS" in scan_focus
    assert "TOP_PCT_GAINERS" in scan_focus


def test_premarket_preparation_has_no_placeholders_or_todos() -> None:
    disallowed = ("placeholder", "todo")
    for text in _iter_strings(POLICY_V2.premarket_preparation):
        lowered = text.lower()
        assert all(token not in lowered for token in disallowed), text
