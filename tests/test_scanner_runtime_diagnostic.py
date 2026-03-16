from __future__ import annotations

from typing import Any, Dict

from src.diagnostics import scanner_runtime_diagnostic


class _FakeProvider:
    source_name = "IBKR_FAKE"

    def __init__(self) -> None:
        self.last_scan_details = {
            "returned_rows": 2,
            "selected_location_code": "STK.NASDAQ",
            "selected_scan_code": "TOP_PERC_GAIN",
            "retry_attempts": 1,
            "retry_exhausted": False,
        }


def test_run_runtime_diagnostic_reports_non_zero_counts(monkeypatch) -> None:
    def _fake_cycle(mode: str, provider: Any) -> Dict[str, Any]:
        assert mode == "READ_ONLY"
        assert provider.source_name == "IBKR_FAKE"
        return {
            "raw_broker_count": 2,
            "survivors_count": 2,
            "watchlist_count": 2,
            "watchlist_k_symbols": ["AAPL", "MSFT"],
            "focus_m_symbols": ["AAPL"],
            "diagnostics": {
                "scanner_flow": {
                    "provider": provider.source_name,
                    "returned_rows": 2,
                    "raw_broker_count": 2,
                    "effective_location_code": "STK.NASDAQ",
                    "effective_scan_code": "TOP_PERC_GAIN",
                    "retry_attempts": 1,
                    "retry_exhausted": False,
                },
                "ibkr_universe": {
                    "effective_location_code": "STK.NASDAQ",
                    "effective_scan_code": "TOP_PERC_GAIN",
                    "retry_attempts": 1,
                    "retry_exhausted": False,
                    "returned_rows": 2,
                },
            },
        }

    monkeypatch.setattr(scanner_runtime_diagnostic, "IbkrScannerProvider", _FakeProvider)
    monkeypatch.setattr(scanner_runtime_diagnostic, "run_scanner_cycle", _fake_cycle)

    payload = scanner_runtime_diagnostic.run_runtime_diagnostic()

    assert payload["raw_broker_count"] > 0
    assert payload["watchlist_count"] > 0
