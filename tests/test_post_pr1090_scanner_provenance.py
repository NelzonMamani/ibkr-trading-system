"""Broker-returned data authority survives provider and scanner boundaries."""
from types import SimpleNamespace

import pytest

from src.scanner.providers.ibkr_provider import IbkrScannerProvider
from src.scanner.scanner_runner import _quote_market_data_provenance, _observed_market_data_summary


def quote_from_snapshot(*, requested="DELAYED", returned="LIVE", confirmed=True):
    snapshot = SimpleNamespace(
        symbol="AEMD", bid=6.1, ask=6.2, last=6.15, close=6.0, volume=3000,
        open=None, high=None, low=None, vwap=None, change_percent=None,
        data_quality_flags=[], timestamp_utc=None, timestamp_source="UNKNOWN",
        received_at_utc="2026-09-18T07:31:00+00:00",
        requested_market_data_type=requested, returned_market_data_type=returned,
        market_data_type_confirmed=confirmed,
        market_data_type_received_at_utc="2026-09-18T07:30:59+00:00",
        request_id=42, snapshot_complete=True,
    )
    provider = IbkrScannerProvider.__new__(IbkrScannerProvider)
    provider._qualified_contract_for_symbol = lambda symbol: None
    provider.market_data_client = SimpleNamespace(snapshot_stock=lambda symbol: snapshot,
                                                 last_snapshot_debug={})
    return provider.get_quote("AEMD")


@pytest.mark.parametrize("requested,returned", [
    ("DELAYED", "LIVE"), ("LIVE", "DELAYED"),
    ("LIVE", "DELAYED_FROZEN"), ("DELAYED", "FROZEN"),
])
def test_scanner_reports_returned_type_instead_of_request(requested, returned):
    quote = quote_from_snapshot(requested=requested, returned=returned)
    context = {"symbol": quote.symbol, **_quote_market_data_provenance(quote)}
    summary = _observed_market_data_summary([context])
    assert summary["mode"] == returned
    assert summary["by_symbol"]["AEMD"] == {
        "requested": requested, "returned": returned, "confirmed": True,
        "type_received_at_utc": "2026-09-18T07:30:59+00:00",
        "request_id": 42, "snapshot_complete": True,
        "quote_timestamp_utc": None, "quote_timestamp_source": "UNKNOWN",
        "quote_received_at_utc": "2026-09-18T07:31:00+00:00",
        "snapshot_evidence": quote.snapshot_evidence,
        "supplemented_fields": {}, "combined_data_type": returned,
    }
    assert context["quote_timestamp_utc"] is None
    assert context["quote_received_at_utc"] == "2026-09-18T07:31:00+00:00"
    assert context["quote_timestamp_source"] == "UNKNOWN"


def test_unconfirmed_default_live_cannot_certify_live_data():
    quote = quote_from_snapshot(requested="LIVE", returned="LIVE", confirmed=False)
    summary = _observed_market_data_summary([
        {"symbol": quote.symbol, **_quote_market_data_provenance(quote)}])
    assert summary["mode"] == "UNKNOWN"
    assert summary["returned_type_counts"] == {"UNKNOWN": 1}


def test_mixed_and_rejected_unknown_quotes_remain_visible():
    contexts = [
        {"symbol": "AEMD", **_quote_market_data_provenance(quote_from_snapshot())},
        {"symbol": "DTSS", **_quote_market_data_provenance(quote_from_snapshot(returned="DELAYED"))},
    ]
    assert _observed_market_data_summary(contexts)["mode"] == "MIXED"
    contexts.append({"symbol": "REJECTED", "snapshot_error": "UNSUBSCRIBED_MARKET_DATA"})
    result = _observed_market_data_summary(contexts)
    assert result["mode"] == "UNKNOWN"
    assert result["returned_type_counts"] == {"LIVE": 1, "DELAYED": 1, "UNKNOWN": 1}
    assert _observed_market_data_summary([])["mode"] == "UNKNOWN"


def test_supplemented_missing_quote_fields_have_separate_unknown_authority():
    from src.scanner.scanner_runner import _merge_snapshot_fields
    context = {"symbol": "AEMD", "bid": None, "ask": None, "last_price": 6.15,
               **_quote_market_data_provenance(quote_from_snapshot())}
    _merge_snapshot_fields(context, {"bid": 6.1, "ask": 6.2, "last_price": 7.0})
    assert context["last_price"] == 6.15
    assert context["bid"] == 6.1
    assert set(context["snapshot_supplemented_fields"]) == {"bid", "ask"}
    result = _observed_market_data_summary([context])
    assert result["mode"] == "UNKNOWN"
    assert result["returned_type_counts"] == {"LIVE": 1}
    assert result["unconfirmed_supplement_count"] == 1
    row = result["by_symbol"]["AEMD"]
    assert row["returned"] == "LIVE"
    assert row["combined_data_type"] == "UNKNOWN"
    assert row["supplemented_fields"]["bid"]["market_data_type_confirmed"] is False
    assert row["supplemented_fields"]["bid"]["timestamp_utc"] is None


def test_rejected_quote_retains_market_time_and_request_evidence():
    context = {"symbol": "AEMD", "drop_reason": "DROP_NO_CATALYST",
               **_quote_market_data_provenance(quote_from_snapshot())}
    context["quote_timestamp_utc"] = "2026-09-18T07:30:00+00:00"
    context["quote_timestamp_source"] = "LAST_TRADE"
    context["snapshot_evidence"] = {"request_started_at_utc": "2026-09-18T07:30:50+00:00"}
    row = _observed_market_data_summary([context])["by_symbol"]["AEMD"]
    assert row["quote_timestamp_utc"] == context["quote_timestamp_utc"]
    assert row["quote_timestamp_source"] == "LAST_TRADE"
    assert row["snapshot_evidence"] == context["snapshot_evidence"]
