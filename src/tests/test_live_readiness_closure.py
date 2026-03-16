from __future__ import annotations

from datetime import datetime, timezone

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.domain.market_snapshot import MarketSnapshot
from src.scanner.session_pct_change import resolve_session_diagnostics
from src.cli.ibkr_scanner_diagnostics import run_diagnostics
from src.cli.live_readiness_check import main as readiness_main
from src.cli.test_trade_pipeline import run_pipeline


def test_snapshot_interface_normalization_wrapper() -> None:
    client = IbkrClient.__new__(IbkrClient)

    def fake_market_snapshot(symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            bid=10.0,
            ask=10.1,
            last=10.05,
            volume=12345,
            asof_utc=datetime.now(timezone.utc),
            market_data_type="LIVE",
            source="IBKR",
        )

    client.get_market_snapshot = fake_market_snapshot  # type: ignore[assignment]
    raw = client.snapshot_stock("AAPL")
    assert raw.symbol == "AAPL"
    assert raw.last == 10.05
    assert raw.close == 10.05
    assert raw.volume == 12345
    assert raw.spread is not None
    assert round(raw.spread, 2) == 0.10


def test_scanner_contract_invariants_reported_in_diagnostics() -> None:
    result = run_diagnostics(dry_run=True)
    contract = result["scanner"]["scanner_contract"]
    assert contract["contract_valid"] is True
    assert 0 <= contract["focus_m"] <= contract["watchlist_k"] <= contract["top_n"]


def test_raw_zero_attribution_payload_available() -> None:
    result = run_diagnostics(dry_run=True)
    payload = result["scanner"]["raw_zero_attribution"]
    required = {
        "provider",
        "broker_returned_zero",
        "instrument",
        "location",
        "scanCode",
        "requested_top_n",
        "broker_rows_requested",
        "effective_internal_processing_limit",
        "translation_or_truncation_occurred",
        "local_gating_applied",
        "local_gating_eliminated_all",
        "raw_broker_count",
        "candidate_count_entering_gates",
        "survivor_count_after_gates",
        "watchlist_count",
        "focus_count",
        "drop_reasons",
    }
    assert required.issubset(payload.keys())


def test_live_readiness_cli_dry_run_success() -> None:
    rc = readiness_main(["--dry-run", "--symbol", "AAPL"])
    assert rc == 0


def test_session_diagnostics_market_clock_when_not_forced() -> None:
    diag = resolve_session_diagnostics()
    assert diag.override_source == "NONE"
    assert diag.reason == "MARKET_CLOCK"


def test_session_diagnostics_forced_source_attribution() -> None:
    diag = resolve_session_diagnostics(forced_session_label="PRE", forced_session_source="TEST_OVERRIDE")
    assert diag.override_source == "TEST_OVERRIDE"
    assert diag.reason == "TEST_OVERRIDE"


def test_pipeline_diagnostics_explicit_no_intent_reporting() -> None:
    result = run_pipeline(symbol="AAPL", dry_run=True, execute_live=False, dangerous_submit_live_order=False)
    assert result["risk"]["first_decision_result"] in {"ALLOW", "DENY"}
    if result["strategy"]["intents_generated"] == 0:
        assert result["risk"]["explicit_no_intent"] is True
        assert result["execution"]["blocked_reason"] == "NO_INTENT"
