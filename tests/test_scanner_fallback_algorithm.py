from src.scanner.providers.ibkr_provider import SCAN_CODES


def test_scanner_fallback_chain_exists():
    assert len(SCAN_CODES) >= 3
