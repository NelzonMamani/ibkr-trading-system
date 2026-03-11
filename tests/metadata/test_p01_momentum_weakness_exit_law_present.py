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


def test_p01_momentum_weakness_and_exit_law_exists_and_has_defaults() -> None:
    model = POLICY_V2.momentum_weakness_and_exit
    tiers = model.pullback_tiers

    assert model is not None
    assert tiers.ideal_pullback_max == 0.30
    assert tiers.caution_pullback_max == 0.40
    assert tiers.hard_warning_pullback_max == 0.50


def test_p01_intrabar_exit_override_has_opening_drive_and_10sec() -> None:
    override = POLICY_V2.momentum_weakness_and_exit.intrabar_exit_override

    assert "OPENING_DRIVE" in set(override.allowed_phases)
    assert "10SEC" in set(override.execution_timeframes)


def test_p01_momentum_weakness_and_exit_law_has_no_placeholders_or_todos() -> None:
    disallowed = ("placeholder", "todo")
    for text in _iter_strings(POLICY_V2.momentum_weakness_and_exit):
        lowered = text.lower()
        assert all(token not in lowered for token in disallowed), text


def test_p01_momentum_weakness_and_exit_doctrinal_strings_non_empty() -> None:
    model = POLICY_V2.momentum_weakness_and_exit

    assert model.pullback_tiers.intrabar_detection_notes.strip()
    assert model.pullback_tiers.calibration_notes.strip()
    assert model.volume_dominance.commentary.strip()
    assert model.volume_dominance.calibration_notes.strip()
    assert model.intrabar_exit_override.doctrine.strip()
    assert model.intrabar_exit_override.calibration_notes.strip()
    assert model.candle_evidence_alignment_notes.strip()
    assert model.notes.strip()
