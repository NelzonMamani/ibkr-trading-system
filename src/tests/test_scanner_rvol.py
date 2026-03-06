from src.scanner.session_pct_change import compute_scanner_rvol


def test_compute_scanner_rvol_basic_ratio() -> None:
    assert compute_scanner_rvol(3_000_000, 2_000_000) == 1.5


def test_compute_scanner_rvol_missing_volume_returns_none() -> None:
    assert compute_scanner_rvol(None, 2_000_000) is None
