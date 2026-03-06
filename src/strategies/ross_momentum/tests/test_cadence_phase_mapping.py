from src.strategies.ross_momentum.strategy import _resolve_ross_pattern_cadence


def test_ross_cadence_phase_mapping() -> None:
    assert _resolve_ross_pattern_cadence("RTH_OPEN")[:2] == ("1m", "10s")
    assert _resolve_ross_pattern_cadence("RTH_MID")[:2] == ("3m", "30s")
    assert _resolve_ross_pattern_cadence("RTH_LATE")[:2] == ("5m", "1m")
