from src.core.engines.trigger_quality_engine import TriggerQualityEngine


def test_trigger_quality_high_for_primary_uptrend_setup():
    result = TriggerQualityEngine.evaluate_trigger_quality(
        trigger={"setup_family_id": "HOD_BREAK", "trigger_quality_flags": []},
        setup={"setup_family_id": "HOD_BREAK", "quality_flags": []},
        structure={"dominant_direction": "UP"},
        levels={"hod": 10.0},
        tradability_context={"session": "REGULAR"},
    )

    assert result["quality_tier"] == "HIGH"
    assert result["quality_score"] >= 0.8
    assert result["rejection_reason"] is None


def test_trigger_quality_medium_for_micro_pullback_unknown_trend():
    result = TriggerQualityEngine.evaluate_trigger_quality(
        trigger={"setup_family_id": "MICRO_PULLBACK", "trigger_quality_flags": []},
        setup={"setup_family_id": "MICRO_PULLBACK", "quality_flags": []},
        structure={"dominant_direction": "UNKNOWN", "pullback_depth": {"anchor_low": 9.8}},
        levels={"ema_9": 10.0},
        tradability_context={"session": "REGULAR"},
    )

    assert result["quality_tier"] == "MEDIUM"
    assert 0.5 <= result["quality_score"] < 0.8


def test_trigger_quality_blocks_generic_fallback():
    result = TriggerQualityEngine.evaluate_trigger_quality(
        trigger={"setup_family_id": "GENERIC_MOMENTUM_PROBE", "trigger_quality_flags": []},
        setup={"setup_family_id": "GENERIC_MOMENTUM_PROBE", "quality_flags": ["FALLBACK_STRUCTURE"]},
        structure={"dominant_direction": "UP"},
        levels={},
        tradability_context={"session": "PRE"},
    )

    assert result["quality_tier"] == "LOW"
    assert result["rejection_reason"] == "fallback_probe_blocked"
    assert "FALLBACK_SETUP" in result["quality_flags"]


def test_trigger_quality_blocks_low_confidence_flags():
    result = TriggerQualityEngine.evaluate_trigger_quality(
        trigger={"setup_family_id": "FIRST_PULLBACK", "trigger_quality_flags": []},
        setup={"setup_family_id": "FIRST_PULLBACK", "quality_flags": ["LOW_CONFIDENCE"]},
        structure={"dominant_direction": "UP", "pullback_depth": {"anchor_low": 9.8}},
        levels={"ema_9": 10.0},
        tradability_context={"session": "REGULAR"},
    )

    assert result["quality_tier"] == "LOW"
    assert result["rejection_reason"] == "low_confidence_flag"
