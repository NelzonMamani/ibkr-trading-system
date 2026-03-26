from __future__ import annotations

from src.scanner.session_pct_change import compute_session_aligned_pct_change


def test_pre_pct_and_gap_reference_last_rth_close() -> None:
    payload = compute_session_aligned_pct_change(
        session_label="PRE",
        cur_last=11.0,
        ref_close_rth=10.0,
        rth_open_price=10.5,
        rth_close_price=10.0,
        ibkr_change_pct=None,
    )
    assert payload.reference_label == "LAST_RTH_CLOSE"
    assert payload.final_pct == 10.0
    assert payload.open_relative_pct_change == 4.76
