from src.scanner.session_pct_change import canonical_session_label, normalize_session_label
from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


def test_power_hour_normalizes_to_regular_late_session() -> None:
    normalized = normalize_session_label("POWER_HOUR")
    assert normalized == "RTH_LATE"
    assert canonical_session_label(normalized) == "RTH_LATE"


def test_ross_session_profile_marks_power_hour_as_context_only_adjustment() -> None:
    quality, confidence_multiplier, preferred_confidence_floor = RossMomentumStrategyV1._session_context_profile(
        session_label="RTH_LATE",
        session_phase="POWER_HOUR",
    )
    assert quality == "LOWER_MOMENTUM / HIGHER_VOLATILITY"
    assert confidence_multiplier < 1.0
    assert preferred_confidence_floor > 0.0
