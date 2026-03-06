from src.scanner.session_pct_change import compute_session_relative_volume_with_provenance


def test_rvol_provenance_pre_session_baseline() -> None:
    payload = compute_session_relative_volume_with_provenance(
        session_label="PRE",
        session_volume=500_000,
        avg_volume_20d=2_000_000,
    )
    assert payload.session_label == "PRE"
    assert payload.baseline == "PREMARKET"
    assert payload.method == "SESSION_VOL / AVG_20D"
    assert payload.value == 0.25


def test_rvol_provenance_closed_no_data() -> None:
    payload = compute_session_relative_volume_with_provenance(
        session_label="CLOSED",
        session_volume=None,
        avg_volume_20d=2_000_000,
    )
    assert payload.session_label == "CLOSED"
    assert payload.baseline == "LAST_KNOWN_SESSION"
    assert payload.value is None
