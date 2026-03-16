from __future__ import annotations

from src.scanner.scanner_runner import run_scanner_cycle
from src.scanner.session_pct_change import resolve_session_diagnostics


class _ZeroProvider:
    source_name = "IBKR"

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_top_gainers(self, limit, request=None):
        return []


def test_session_diagnostics_market_clock_when_no_override() -> None:
    diag = resolve_session_diagnostics()
    assert diag.reason == "MARKET_CLOCK"
    assert diag.override_source == "NONE"


def test_scanner_raw_zero_attribution_is_printed(capsys) -> None:
    payload = run_scanner_cycle(mode="LIVE", provider=_ZeroProvider())
    assert payload is not None
    out = capsys.readouterr().out
    assert "[SCANNER][RAW_ZERO]" in out
    assert "broker_returned_zero=True" in out
    assert "requested_top_n=" in out
    assert "broker_rows_requested=" in out
    assert "effective_internal_processing_limit=" in out


def test_session_mode_logs_source_when_forced(capsys) -> None:
    run_scanner_cycle(mode="READ_ONLY", provider=_ZeroProvider(), forced_session_label="PRE", forced_session_source="TEST_OVERRIDE")
    out = capsys.readouterr().out
    assert "reason=TEST_OVERRIDE" in out
    assert "forced_source=TEST_OVERRIDE" in out


def test_session_mode_logs_market_clock_when_not_forced(capsys) -> None:
    run_scanner_cycle(mode="READ_ONLY", provider=_ZeroProvider())
    out = capsys.readouterr().out
    assert "[SESSION][MODE]" in out
    assert "reason=MARKET_CLOCK" in out
    assert "forced=NONE" in out
    assert "forced_source=NONE" in out
