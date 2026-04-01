from src.core.tradeability.tradeability_gate import evaluate_tradeability
from src.scanner.session_pct_change import canonical_session_label, compute_session_relative_volume_with_provenance


def test_ovn_session_remains_canonical_overnight() -> None:
    assert canonical_session_label("OVN") == "OVN"


def test_rvol_disabled_for_overnight_session() -> None:
    payload = compute_session_relative_volume_with_provenance(
        session_label="OVN",
        session_volume=1000,
        avg_volume_20d=1_000_000,
        persisted_rvol=2.5,
    )
    assert payload.value is None
    assert payload.method == "DISABLED_FOR_SESSION"


def test_tradeability_gate_rejects_low_absolute_volume() -> None:
    decision = evaluate_tradeability(
        {
            "session": "RTH_OPEN",
            "volume": 1000,
            "dollar_volume": 10_000,
            "spread_pct": 0.01,
            "bid": 10.0,
            "ask": 10.01,
        }
    )
    assert not decision.accepted
    assert decision.reason == "LOW_ABSOLUTE_VOLUME"
