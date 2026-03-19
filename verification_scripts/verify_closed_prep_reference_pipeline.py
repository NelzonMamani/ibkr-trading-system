from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.scanner.candidate_identity import CandidateIdentity
from src.scanner.reference_resolver import CanonicalReferenceResolver
from src.scanner.session_pct_change import compute_session_aligned_pct_change, resolve_session_diagnostics


class _Bar:
    def __init__(self, trading_date: str, close: float, volume: int = 100_000) -> None:
        self.date = trading_date
        self.close = close
        self.volume = volume


class _Provider:
    source_name = "IBKR"

    def __init__(self, bars) -> None:
        self.bars = list(bars)

    def qualifyContracts(self, contract):
        contract.conId = 42
        contract.primaryExchange = "NASDAQ"
        contract.exchange = "SMART"
        return [contract]

    def get_daily_bars(self, identity, lookback_days: int):
        return list(self.bars)


def main() -> None:
    probe = datetime(2026, 3, 19, 0, 20, tzinfo=timezone.utc)
    diag = resolve_session_diagnostics(probe)
    assert diag.resolved_session == "OVN", diag
    assert diag.canonical_session == "CLOSED", diag

    pct = compute_session_aligned_pct_change(
        session_label="CLOSED",
        cur_last=1.74,
        ref_close_rth=1.20,
        rth_open_price=None,
        rth_close_price=1.20,
        ibkr_change_pct=None,
    )
    assert pct.reference_price == 1.20
    assert pct.final_pct == 45.0

    resolver = CanonicalReferenceResolver()
    result = resolver.resolve(
        identity=CandidateIdentity(symbol="MDAI", con_id=42, exchange="SMART", primary_exchange="NASDAQ"),
        provider=_Provider([_Bar("2026-03-18", 1.20)]),
        session_label="CLOSED",
        current_volume=780,
        intraday_avg_volume_20d=None,
        current_last_price=1.74,
        rth_open_price=None,
        rth_close_price=1.20,
        ibkr_change_pct=None,
        persisted_pct_change=None,
    )
    assert result.reference_price == 1.20
    assert result.reference_source == "IBKR_DAILY_BARS"
    print("verify_closed_prep_reference_pipeline: PASS")


if __name__ == "__main__":
    main()
