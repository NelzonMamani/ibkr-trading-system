from types import SimpleNamespace


def test_build_symbol_context_backward_compatibility():
    from src.scanner.scanner_runner import _build_symbol_context

    class DummyProvider:
        source_name = "MOCK"
        last_scan_details = {}

        def get_quote(self, symbol):
            return SimpleNamespace(
                last=10.0,
                bid=9.9,
                ask=10.1,
                close=9.5,
                open=9.7,
                high=10.2,
                low=9.4,
                volume=1000,
                vwap=10.0,
                change_percent=None,
                data_quality_flags=[],
                persisted_rvol=None,
                persisted_pct_change=None,
            )

        def get_intraday_stats(self, symbol):
            return SimpleNamespace(
                current_intraday_volume=1000,
                average_daily_volume_20d=10000,
                average_daily_volume_window_days=20,
                day_high=10.3,
            )

    context = _build_symbol_context(
        provider=DummyProvider(),
        symbol="TEST",
        session_label="PRE",
    )

    assert context is not None
    assert "session_contract" in context
    assert context["canonical_session"] == "PRE"
