from __future__ import annotations

import time

from src.config.config_resolver import set_config_overrides
from src.scanner.providers.base import IntradayStats, QuoteData
from src.scanner.scanner_contract import ScannerRequest, validate_scanner_request
from src.scanner.scanner_runner import reset_scanner_runtime_state, run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy, UniverseSource


def test_validate_scanner_request_flags_missing_fields():
    request = ScannerRequest(
        strategy_name="",
        policy_name="",
        ranking_intent="",
        session_phase=None,
        universe_source=UniverseSource.IBKR_TOP_GAINERS,
        ibkr_scan_code="",
        requested_top_n=0,
        above_price=10.0,
        below_price=5.0,
        optional_symbols_override=[],
        region=None,
        instrument="",
        location_code="",
        exchanges=[""],
    )

    errors = validate_scanner_request(request)

    assert "strategy_name must be non-empty" in errors
    assert "policy_name must be non-empty" in errors
    assert "ranking_intent must be non-empty" in errors
    assert "requested_top_n must be > 0" in errors
    assert "ibkr_scan_code must be non-empty" in errors
    assert "instrument must be non-empty" in errors
    assert "location_code must be non-empty" in errors
    assert "above_price must be <= below_price" in errors
    assert "optional_symbols_override must include at least one symbol" in errors
    assert "exchanges must include at least one exchange" in errors


def test_run_scanner_cycle_rejects_invalid_request():
    policy = RossMomentumPolicy().stock_selection
    request = ScannerRequest(
        strategy_name=policy.policy_name,
        policy_name=policy.policy_name,
        ranking_intent=policy.ranking_intent,
        session_phase=None,
        universe_source=UniverseSource.IBKR_TOP_GAINERS,
        ibkr_scan_code="",
        requested_top_n=0,
        above_price=policy.price_min,
        below_price=policy.price_max,
        optional_symbols_override=None,
        region=None,
        instrument=policy.universe.instrument,
        location_code=policy.universe.location_code,
        exchanges=None,
    )

    payload = run_scanner_cycle(
        mode="READONLY",
        policy=policy,
        scanner_request=request,
    )

    diagnostics = payload.get("diagnostics", {})
    assert diagnostics.get("scanner_request_valid") is False
    assert payload.get("topn_count") == 0
    assert payload.get("symbols") == []


class _BoundedRuntimeProvider:
    source_name = "IBKR"

    def __init__(self) -> None:
        self.connection_manager = None
        self.last_scan_details = {}
        self.quote_calls: list[str] = []

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_top_gainers(self, limit, request=None):
        self.last_scan_details = {
            "requested_location_code": "STK.US.MAJOR",
            "requested_scan_code": "TOP_PERC_GAIN",
            "selected_location_code": "STK.US.MAJOR",
            "selected_scan_code": "TOP_PERC_GAIN",
            "retry_attempts": 1,
            "retry_exhausted": False,
            "returned_rows": 2,
        }
        return ["BOUND1", "BOUND2"]

    def get_quote(self, symbol: str) -> QuoteData:
        self.quote_calls.append(symbol)
        raise AssertionError("runtime deadline should stop before quote enrichment")

    def get_prev_close(self, symbol: str):
        raise AssertionError("runtime deadline should stop before quote enrichment")

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        raise AssertionError("runtime deadline should stop before intraday enrichment")

    def get_float(self, symbol: str):
        raise AssertionError("runtime deadline should stop before float lookup")


def test_run_scanner_cycle_runtime_deadline_returns_bounded_payload_without_symbol_enrichment():
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "RUN_MODE_EFFECTIVE": "READ_ONLY",
            "NEWS_ENABLED": False,
        }
    )
    reset_scanner_runtime_state(clear_persistent_provider=True)
    try:
        policy = RossMomentumPolicy().stock_selection
        request = ScannerRequest(
            strategy_name=policy.policy_name,
            policy_name=policy.policy_name,
            ranking_intent=policy.ranking_intent,
            session_phase=None,
            universe_source=UniverseSource.IBKR_TOP_GAINERS,
            ibkr_scan_code="TOP_PERC_GAIN",
            requested_top_n=2,
            above_price=policy.price_min,
            below_price=policy.price_max,
            optional_symbols_override=None,
            region="US",
            instrument=policy.universe.instrument,
            location_code=policy.universe.location_code,
            exchanges=None,
        )
        provider = _BoundedRuntimeProvider()

        payload = run_scanner_cycle(
            mode="READ_ONLY",
            policy=policy,
            scanner_request=request,
            provider=provider,
            runtime_deadline_s=time.monotonic() - 1.0,
        )
    finally:
        reset_scanner_runtime_state(clear_persistent_provider=True)
        set_config_overrides({})

    runtime_bound = payload["diagnostics"]["scanner_runtime_bound"]
    market_snapshot = payload["diagnostics"]["market_snapshot_enrichment"]
    assert payload["topn_count"] == 2
    assert payload["symbols"] == []
    assert payload["watchlist_k_symbols"] == []
    assert provider.quote_calls == []
    assert runtime_bound["active"] is True
    assert runtime_bound["stopped"] is True
    assert runtime_bound["stop_stage"] == "pre_market_snapshot_enrichment"
    assert runtime_bound["stop_reason"] == "RUNTIME_DEADLINE_REACHED"
    assert runtime_bound["completed_returned_payload"] is True
    assert market_snapshot["requested_symbols"] == 0
    assert market_snapshot["skipped_due_to_runtime_bound"] is True
