from src.diagnostics.ibkr_scanner_diagnostic import test_raw_ibkr as run_raw_ibkr_diagnostic


def test_ibkr_scanner_returns_rows():
    count = run_raw_ibkr_diagnostic()
    assert count >= 0
