from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
        return SimpleNamespace(
            current_intraday_volume=current,
            average_daily_volume_20d=None,
            average_daily_volume_window_days=None,
            relative_volume=None,
            day_high=None,
        )

    def get_prev_close(self, symbol: str):
        return {"BRK B": 10.0, "ABC PRA": 8.0}.get(symbol)

    def get_previous_rth_close(self, identity):
        return self.get_prev_close(getattr(identity, "symbol", identity))

    def get_average_daily_volume(self, identity, window: int):
        avg = {"BRK B": 1_000_000, "ABC PRA": 500_000}[getattr(identity, "symbol", identity)]
        return avg, min(window, 20)

    def get_daily_bars(self, identity, lookback_days: int):
        symbol = getattr(identity, "symbol", identity)
        prev = self.get_prev_close(symbol)
        avg, window = self.get_average_daily_volume(identity, lookback_days)
        return [SimpleNamespace(date=f"2026-01-{idx+1:02d}", close=prev, volume=avg) for idx in range(window)]


def main() -> None:
    provider = DiagnosticProvider()
    contexts = []
    failures: list[str] = []
    for symbol in ("BRK B", "ABC PRA"):
        context = _build_symbol_context(provider, symbol, "PRE", float_cache={}, include_pct_change=True)
        if context:
            contexts.append(context)
            checks = {
                "reference_price": context.get("reference_price") is not None,
                "pct_change": context.get("pct_change") is not None,
                "gap_pct_resolved": context.get("gap_pct_resolved") is not None,
                "avg_volume_20d": context.get("avg_volume_20d") is not None,
                "rvol_ready": context.get("rvol_discovery") is not None or context.get("rvol_phase") is not None,
            }
            for name, passed in checks.items():
                status = "PASS" if passed else "FAIL"
                print(f"[{status}] symbol={symbol} check={name} value={context.get(name)}")
                if not passed:
                    failures.append(f"{symbol}:{name}")
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
    if failures:
        print(f"VERDICT: FAIL failures={failures}")
        raise SystemExit(1)
    print("VERDICT: PASS")


if __name__ == "__main__":
    main()
