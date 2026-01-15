from src.scanner.scanner_runner import run_scanner_cycle


def test_scanner_contract_prints_lists(capsys):
    payload = run_scanner_cycle(mode="READONLY")
    output = capsys.readouterr().out
    assert "WATCHLIST_K:" in output or "EMPTY WATCHLIST (valid)" in output
    assert "FOCUS_M:" in output or "EMPTY WATCHLIST (valid)" in output
    assert "watchlist_k" in payload
    assert "focus_m" in payload
