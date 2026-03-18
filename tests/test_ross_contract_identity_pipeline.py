from __future__ import annotations

from types import SimpleNamespace

from ibapi.client import EClient
from ibapi.contract import Contract, ContractDetails

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.market_data.market_snapshot_enricher import MarketSnapshotEnricher
from src.scanner.candidate_identity import CandidateIdentity, bridge_identity_keys
from src.scanner.scanner_runner import (
    GateThresholds,
    _build_symbol_context,
    _enrichment_audit_summary,
    _evaluate_focus_gates,
    _gate_outcome_summary,
    _populate_pct_change,
)


class DummyConnectionManager:
    def __init__(self, client):
        self._client = client

    def get_client(self):
        return self._client


class DummyProvider:
    def __init__(self) -> None:
        self.source_name = "MOCK"
        self.last_scan_details = {
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
        return SimpleNamespace(
            bid=10.9,
            ask=11.1,
            last=11.0,
            close=None,
            open=10.5,
            high=11.5,
            low=10.25,
            vwap=10.8,
            volume=250_000,
            change_percent=None,
            persisted_pct_change=None,
            persisted_rvol=None,
            data_quality_flags=[],
        )

    def get_intraday_stats(self, symbol: str):
        return SimpleNamespace(
            current_intraday_volume=250_000,
            average_daily_volume_20d=1_000_000,
            average_daily_volume_window_days=20,
            relative_volume=2.5,
            day_high=11.5,
        )

    def get_prev_close(self, symbol: str):
        mapping = {"BRK B": 10.0, "ABC PRA": 8.0}
        return mapping.get(symbol)


def _build_client() -> IbkrClient:
    return IbkrClient(
        host="127.0.0.1",
        port=4001,
        client_id=1,
        snapshot_timeout_seconds=1,
        market_data_type="DELAYED",
        readonly_enabled=True,
    )


def test_scanner_candidate_snapshot_merge_preserves_contract_identity(monkeypatch):
    client = _build_client()

    def fake_resolve(symbol: str, exchange: str = "SMART", currency: str = "USD"):
        resolved = Contract()
        resolved.symbol = "BRK"
        resolved.localSymbol = symbol
        resolved.tradingClass = symbol
        resolved.secType = "STK"
        resolved.exchange = exchange
        resolved.currency = currency
        resolved.conId = 101
        details = ContractDetails()
        details.contract = resolved
        return details

    def fake_req_mkt_data(self, req_id, contract, generic_tick_list, snapshot, regulatory_snapshot, options):
        self.tickPrice(req_id, 4, 11.0, None)
        self.tickPrice(req_id, 1, 10.9, None)
        self.tickPrice(req_id, 2, 11.1, None)
        self.tickSize(req_id, 8, 250000)

    monkeypatch.setattr(client, "resolve_contract", fake_resolve)
    monkeypatch.setattr(EClient, "reqMktData", fake_req_mkt_data)
    monkeypatch.setattr(EClient, "cancelMktData", lambda self, req_id: None)

    enricher = MarketSnapshotEnricher(connection_manager=DummyConnectionManager(client), batch_timeout_seconds=0.2)
    snapshots = enricher.fetch_snapshots(
        ["BRK B"],
        contract_details_by_symbol={
            "BRK B": {
                "symbol": "BRK B",
                "secType": "STK",
                "conId": 101,
                "exchange": "SMART",
                "primaryExchange": "NYSE",
                "tradingClass": "BRK B",
                "localSymbol": "BRK B",
                "currency": "USD",
            }
        },
    )

    assert snapshots["BRK B"]["last_price"] == 11.0
    assert enricher.last_fetch_diagnostics["BRK B"]["identity_key"] == "conid:101"


def test_reference_close_hydration_merges_into_same_candidate_and_pct_change_becomes_non_null():
    provider = DummyProvider()
    context = {
        "symbol": "BRK B",
        "session": "PRE",
        "last_price": 11.0,
        "prev_close": None,
        "rth_open_price": 10.5,
        "rth_close_price": None,
        "ibkr_change_pct": None,
        "persisted_pct_change": None,
        "con_id": 101,
        "exchange": "SMART",
        "primary_exchange": "NYSE",
        "trading_class": "BRK B",
        "local_symbol": "BRK B",
        "currency": "USD",
        "instrument_type": "STK",
        "data_quality_flags": [],
    }

    _populate_pct_change(context, provider)

    assert context["reference_price"] == 10.0
    assert context["pct_change"] == 10.0
    assert context["gap_pct_resolved"] == round(((11.0 - 10.5) / 10.5) * 100.0, 2)


def test_rvol_baseline_hydration_merges_into_same_candidate_and_focus_gate_reads_it():
    provider = DummyProvider()
    context = _build_symbol_context(provider, "BRK B", "PRE", float_cache={}, include_pct_change=True)
    assert context is not None
    context.update(
        {
            "catalyst_present": True,
            "news_present": True,
            "spread_pct": 0.01,
            "float_shares": 5_000_000,
        }
    )
    thresholds = GateThresholds(
        min_price=1.0,
        max_price=20.0,
        min_pct_change=5.0,
        max_pct_change=None,
        watchlist_rvol_min=0.5,
        focus_rvol_min=0.5,
        focus_volume_min=1000,
        focus_volume_min_early_rth=1000,
        focus_volume_min_early_rth_ratio=0.1,
        min_volume=1000,
        min_premarket_volume=1000,
        max_float=50_000_000,
        spread_max_pct=0.05,
        min_dollar_volume=None,
        require_price=True,
        require_bid_ask=False,
        require_catalyst=False,
        allow_halts=True,
        allow_ssr=True,
        allow_unknown_float=True,
    )

    assert context["avg_volume_20d"] == 1_000_000
    assert context["rvol_discovery"] is not None
    assert _evaluate_focus_gates(context, thresholds) is None


def test_symbols_with_unusual_forms_do_not_break_identity_alias_mapping():
    identity = CandidateIdentity.from_mapping(
        {
            "symbol": "ABC PRA",
            "conId": 202,
            "secType": "STK",
            "exchange": "SMART",
            "primaryExchange": "NASDAQ",
            "tradingClass": "ABC PRA",
            "localSymbol": "ABC PRA",
            "currency": "USD",
        }
    )

    assert identity.key == "conid:202"
    assert bridge_identity_keys(identity) == ("conid:202", "symbol:ABC PRA")


def test_pre_session_candidate_with_valid_prior_close_and_snapshot_price_produces_pct_change_and_gap():
    provider = DummyProvider()
    context = _build_symbol_context(provider, "BRK B", "PRE", float_cache={}, include_pct_change=True)

    assert context is not None
    assert context["reference_label"] == "LAST_RTH_CLOSE"
    assert context["pct_change_resolved"] == 10.0
    assert context["gap_pct_resolved"] == round(((11.0 - 10.5) / 10.5) * 100.0, 2)


def test_summary_audit_fields_distinguish_true_gate_passes_from_prep_backfill_and_seeding():
    contexts = [
        {"symbol": "LIVE", "promotion_reason": "LIVE_SCAN", "prep_seeded": False, "reference_price": 10.0, "pct_change": 5.0, "gap_pct_resolved": 5.0, "rvol_discovery": 2.0, "float_shares": 1_000_000, "last_price": 10.5},
        {"symbol": "BACK", "promotion_reason": "PREP_CONTEXT_BACKFILL", "prep_seeded": False},
        {"symbol": "SEED", "promotion_reason": "PREP_WATCHLIST_SEEDED", "prep_seeded": True},
    ]

    enrich = _enrichment_audit_summary(contexts)
    summary = _gate_outcome_summary(contexts)

    assert enrich["reference_ok"] == 1
    assert enrich["pct_ready"] == 1
    assert summary == {"true_gate_pass_count": 1, "backfill_count": 1, "seeded_count": 1}
