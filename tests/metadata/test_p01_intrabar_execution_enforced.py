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


def test_intrabar_execution_present_and_nontrivial() -> None:
    intrabar = POLICY_V2.intrabar_execution

    assert intrabar is not None
    phase_ids = {phase.phase_id for phase in intrabar.phase_specs}
    assert "OPENING_DRIVE" in phase_ids
    assert "LATE_DAY" in phase_ids


def test_intrabar_execution_opening_drive_mentions_10sec() -> None:
    opening_drive_map = next(
        tf_map for tf_map in POLICY_V2.intrabar_execution.timeframe_map if tf_map.phase_id == "OPENING_DRIVE"
    )

    assert "10SEC" in opening_drive_map.execution_timeframes
    assert "10sec" in opening_drive_map.candle_close_policy.lower()


def test_intrabar_execution_late_day_mentions_timeframe_compression() -> None:
    late_day_map = next(
        tf_map for tf_map in POLICY_V2.intrabar_execution.timeframe_map if tf_map.phase_id == "LATE_DAY"
    )

    assert "timeframe compression" in late_day_map.candle_close_policy.lower()


def test_intrabar_execution_has_no_placeholders_or_todos() -> None:
    disallowed = ("placeholder", "todo")
    for text in _iter_strings(POLICY_V2.intrabar_execution):
        lowered = text.lower()
        assert all(token not in lowered for token in disallowed), text
