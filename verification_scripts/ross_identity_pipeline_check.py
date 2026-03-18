from __future__ import annotations

from types import SimpleNamespace

from src.scanner.scanner_runner import _build_symbol_context, _enrichment_audit_summary, _gate_outcome_summary


class DiagnosticProvider:
    source_name = "MOCK"
    last_scan_details = {
        "symbol_details": {
            "BRK B": {
                "conId": 101,
                "secType": "STK",
                "exchange": "SMART",
                "primaryExchange": "NYSE",
                "tradingClass": "BRK B",
                "localSymbol": "BRK B",
                "currency": "USD",
            },
            "ABC PRA": {
                "conId": 202,
                "secType": "STK",
                "exchange": "SMART",
                "primaryExchange": "NASDAQ",
                "tradingClass": "ABC PRA",
                "localSymbol": "ABC PRA",
                "currency": "USD",
            },
        }
    }

    def get_quote(self, symbol: str):
        payload = {
            "BRK B": (11.0, 10.5, None, 250_000),
            "ABC PRA": (8.8, 8.3, None, 150_000),
        }[symbol]
        last, open_, close, volume = payload
        return SimpleNamespace(
            bid=last - 0.1,
            ask=last + 0.1,
            last=last,
            close=close,
            open=open_,
            high=last + 0.4,
            low=open_ - 0.2,
            vwap=(last + open_) / 2,
            volume=volume,
            change_percent=None,
            persisted_pct_change=None,
            persisted_rvol=None,
            data_quality_flags=[],
        )

    def get_intraday_stats(self, symbol: str):
        current = {"BRK B": 250_000, "ABC PRA": 150_000}[symbol]
        avg = {"BRK B": 1_000_000, "ABC PRA": 500_000}[symbol]
        return SimpleNamespace(
            current_intraday_volume=current,
            average_daily_volume_20d=avg,
            average_daily_volume_window_days=20,
            relative_volume=round(current / avg, 2),
            day_high=None,
        )

    def get_prev_close(self, symbol: str):
        return {"BRK B": 10.0, "ABC PRA": 8.0}.get(symbol)


def main() -> None:
    provider = DiagnosticProvider()
    contexts = []
    for symbol in ("BRK B", "ABC PRA"):
        context = _build_symbol_context(provider, symbol, "PRE", float_cache={}, include_pct_change=True)
        if context:
            contexts.append(context)
    enrich = _enrichment_audit_summary(contexts)
    gate = _gate_outcome_summary([
        {**context, "promotion_reason": "LIVE_SCAN", "prep_seeded": False} for context in contexts
    ])
    print(
        "[ENRICH][SUMMARY] "
        f"candidates={enrich['candidates']} snapshot_ok={enrich['snapshot_ok']} reference_ok={enrich['reference_ok']} "
        f"pct_ready={enrich['pct_ready']} gap_ready={enrich['gap_ready']} rvol_ready={enrich['rvol_ready']} "
        f"float_ready={enrich['float_ready']} identity_merge_failures={enrich['identity_merge_failures']}"
    )
    print(
        "[SCANNER][SUMMARY] "
        f"true_gate_pass_count={gate['true_gate_pass_count']} backfill_count={gate['backfill_count']} seeded_count={gate['seeded_count']}"
    )
    for context in contexts:
        print(
            "[VERIFY] "
            f"symbol={context['symbol']} reference_price={context['reference_price']} pct_change={context['pct_change']} "
            f"gap_pct={context['gap_pct_resolved']} rvol_discovery={context['rvol_discovery']} rvol_phase={context['rvol_phase']}"
        )


if __name__ == "__main__":
    main()
