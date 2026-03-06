from types import SimpleNamespace

from src.scanner.scanner_runner import _build_symbol_context


class _ProviderStub:
    source_name = "MOCK"
    last_scan_details = {}

    def get_quote(self, symbol: str):
        return SimpleNamespace(
            bid=11.9,
            ask=12.1,
            last=12.0,
            close=11.0,
            volume=None,
            vwap=None,
            open=11.2,
            change_percent=None,
            data_quality_flags=[],
            persisted_rvol=None,
            persisted_pct_change=None,
        )

    def get_intraday_stats(self, symbol: str):
        return SimpleNamespace(
            current_intraday_volume=100000,
            average_daily_volume_20d=500000,
            average_daily_volume_window_days=20,
            relative_volume=2.0,
            day_high=10.0,
        )


def test_hod_pct_metric_calculation() -> None:
    context = _build_symbol_context(
        provider=_ProviderStub(),
        symbol="TEST",
        session_label="PRE",
        float_cache={},
        include_pct_change=False,
    )

    assert context is not None
    assert context["last_price"] == 12.0
    assert context["hod_pct"] == 20.0
