from __future__ import annotations

from src.scanner import scanner_runner
from src.scanner.reference_resolver import resolve_reference_bundle


def _base_context(*, prep_only: bool, rvol: float | None) -> dict:
    return {
        "symbol": "TEST",
        "session": "AH" if prep_only else "PRE",
        "pct_change": 12.0,
        "scanner_rvol": rvol,
        "float_shares": None,
        "prep_only": prep_only,
        "execution_ready": not prep_only,
    }


def test_watchlist_gate_defers_rvol_for_prep_only() -> None:
    thresholds = scanner_runner.GateThresholds(
        min_price=1.0,
        max_price=20.0,
        min_pct_change=5.0,
        max_pct_change=None,
        watchlist_rvol_min=2.0,
        focus_rvol_min=5.0,
        min_volume=100_000,
        min_premarket_volume=50_000,
        max_float=20_000_000,
        spread_max_pct=None,
        min_dollar_volume=None,
        require_price=False,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=False,
    )
    context = _base_context(prep_only=True, rvol=0.2)
    drop = scanner_runner._evaluate_watchlist_gates(context, thresholds)
    assert drop is None


def test_watchlist_gate_keeps_live_rvol_strict_for_pre() -> None:
    thresholds = scanner_runner.GateThresholds(
        min_price=1.0,
        max_price=20.0,
        min_pct_change=5.0,
        max_pct_change=None,
        watchlist_rvol_min=2.0,
        focus_rvol_min=5.0,
        min_volume=100_000,
        min_premarket_volume=50_000,
        max_float=20_000_000,
        spread_max_pct=None,
        min_dollar_volume=None,
        require_price=False,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=False,
    )
    context = _base_context(prep_only=False, rvol=0.2)
    drop = scanner_runner._evaluate_watchlist_gates(context, thresholds)
    assert drop is None


def test_prep_only_bundle_never_execution_ready() -> None:
    after = resolve_reference_bundle(
        session_label="AH",
        reference_price=10.0,
        reference_label="LAST_RTH_CLOSE",
        pct_change=10.0,
        pct_source="LIVE_OR_IBKR",
        gap_pct=1.0,
        gap_source="PREP_CONTEXT",
    )
    pre = resolve_reference_bundle(
        session_label="PRE",
        reference_price=10.0,
        reference_label="LAST_RTH_CLOSE",
        pct_change=10.0,
        pct_source="LIVE_OR_IBKR",
        gap_pct=1.0,
        gap_source="SESSION_OPEN_VS_REF",
    )
    assert after.prep_only is True
    assert after.execution_ready is False
    assert pre.prep_only is False
    assert pre.execution_ready is True


def test_watchlist_gate_blocks_etf_symbols() -> None:
    context = {"symbol": "SPY", "instrument_type": "ETF"}
    assert scanner_runner._is_etf_context(context) is True
