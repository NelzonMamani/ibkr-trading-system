from src.scanner.session_pct_change import (
    compute_session_aligned_pct_change,
    compute_session_relative_volume_with_provenance,
)


def test_pct_change_pre_and_rth_use_last_rth_close() -> None:
    pre = compute_session_aligned_pct_change(
        session_label="PRE",
        cur_last=11.0,
        ref_close_rth=10.0,
        rth_open_price=10.5,
        rth_close_price=10.0,
        ibkr_change_pct=None,
    )
    rth = compute_session_aligned_pct_change(
        session_label="RTH_OPEN",
        cur_last=11.0,
        ref_close_rth=10.0,
        rth_open_price=10.5,
        rth_close_price=10.0,
        ibkr_change_pct=None,
    )

    assert pre.reference_label == "LAST_RTH_CLOSE"
    assert pre.final_pct == 10.0
    assert rth.reference_label == "LAST_RTH_CLOSE"
    assert rth.final_pct == 10.0
    assert rth.open_relative_pct_change == 4.76


def test_pct_change_weekend_uses_last_rth_close_fallback() -> None:
    closed = compute_session_aligned_pct_change(
        session_label="WEEKEND",
        cur_last=12.0,
        ref_close_rth=10.0,
        rth_open_price=10.5,
        rth_close_price=10.0,
        ibkr_change_pct=99.0,
        persisted_pct_change=7.25,
    )

    assert closed.reference_label == "LAST_RTH_CLOSE"
    assert closed.reference_price == 10.0
    assert closed.pct_source == "CALC(SESSION_REF)"
    assert closed.final_pct == 20.0


def test_pct_change_closed_uses_last_rth_close_fallback() -> None:
    closed = compute_session_aligned_pct_change(
        session_label="CLOSED",
        cur_last=12.0,
        ref_close_rth=10.0,
        rth_open_price=10.5,
        rth_close_price=10.0,
        ibkr_change_pct=None,
    )

    assert closed.reference_label == "LAST_RTH_CLOSE"
    assert closed.reference_price == 10.0
    assert closed.pct_source == "CALC(SESSION_REF)"
    assert closed.final_pct == 20.0


def test_rvol_provenance_pre_session_baseline() -> None:
    payload = compute_session_relative_volume_with_provenance(
        session_label="PRE",
        session_volume=500_000,
        avg_volume_20d=2_000_000,
    )
    assert payload.session_label == "PRE"
    assert payload.baseline == "LAST_RTH_CLOSE_SESSION_TIME"
    assert payload.method == "SESSION_NORMALIZED_RVOL"
    assert payload.value is not None


def test_rvol_provenance_closed_uses_persisted() -> None:
    payload = compute_session_relative_volume_with_provenance(
        session_label="OVN",
        session_volume=None,
        avg_volume_20d=2_000_000,
        persisted_rvol=3.4,
    )
    assert payload.session_label == "OVN"
    assert payload.baseline == "LAST_SESSION_REFERENCE"
    assert payload.method == "PERSISTED_RVOL"
    assert payload.value == 3.4
