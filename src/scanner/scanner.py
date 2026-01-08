"""
Scanner module skeleton for illustrating how market candidates could be produced.

Phase 3: Skeleton status only — this module contains placeholders for teaching.
No real scanning logic is implemented; outputs are empty for demonstration.
"""

from __future__ import annotations

import os
from typing import List

from brokers import IbkrBroker
from config.runtime_config import RunMode, get_ibkr_readonly_enabled, get_run_mode
from config.system_config import get_current_market_session
from models.data_models import ScannerCandidate


class Scanner:
    """Minimal scanner placeholder with instructional logging."""

    def __init__(self) -> None:
        self.run_mode = get_run_mode()
        self.ibkr_readonly_enabled = get_ibkr_readonly_enabled()
        self.scan_symbols = self._resolve_scan_symbols()
        print("[BOOT] Scanner instantiated — phase 4 teaching placeholder (static outputs)")

    @staticmethod
    def _resolve_scan_symbols() -> List[str]:
        raw = (os.getenv("IBKR_SCAN_SYMBOLS") or "").strip()
        if not raw:
            return []
        return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]

    def run_scan_cycle(self) -> List[ScannerCandidate]:
        """
        Demonstrate how a scan cycle would be invoked in a real system.

        Returns a deterministic list of hard-coded teaching candidates to let
        downstream modules be exercised without touching real markets.
        """

        if (
            self.run_mode == RunMode.LIVE_READ_ONLY
            and self.ibkr_readonly_enabled
            and self.scan_symbols
        ):
            return self._run_live_readonly_scan()

        print("[SCAN] Teaching scan started — using static, fake symbols only")
        print(
            "[SCAN] These candidates are simulated for instruction; no live data, "
            "no randomness, no external calls"
        )
        return self._static_candidates()

    def _run_live_readonly_scan(self) -> List[ScannerCandidate]:
        print("[SCAN] LIVE READ-ONLY scan started — using IBKR market snapshots")
        if IbkrBroker is None:
            print("[SCAN] IBKR broker unavailable; falling back to static candidates.")
            return self._static_candidates()
        broker = IbkrBroker()
        session = get_current_market_session()
        candidates: List[ScannerCandidate] = []
        try:
            broker.connect()
            for symbol in self.scan_symbols:
                snapshot = broker.get_market_snapshot(symbol)
                bid = snapshot.bid
                ask = snapshot.ask
                last = snapshot.last
                spread = None
                if bid is not None and ask is not None:
                    spread = round(ask - bid, 4)
                reference_price = (
                    last
                    if last is not None
                    else round((bid + ask) / 2, 4)
                    if bid is not None and ask is not None
                    else bid
                    if bid is not None
                    else ask
                    if ask is not None
                    else 0.0
                )
                print(
                    "[SCAN] IBKR snapshot "
                    f"symbol={symbol} bid={bid} ask={ask} last={last} "
                    f"spread={spread} session={session}"
                )
                candidates.append(
                    ScannerCandidate(
                        symbol=symbol,
                        price=float(reference_price),
                        gap_percent=0.0,
                        rvol=0.0,
                        float_millions=0.0,
                        rationale=(
                            "LIVE_READ_ONLY snapshot from IBKR; gaps/rVol/float "
                            "placeholders for phase 15 validation."
                        ),
                    )
                )
        finally:
            broker.disconnect()
        print("[SCAN] Returning IBKR-backed candidates for downstream teaching modules")
        return candidates

    def _static_candidates(self) -> List[ScannerCandidate]:
        candidates: List[ScannerCandidate] = [
            ScannerCandidate(
                symbol="ABC",
                price=12.35,
                gap_percent=8.4,
                rvol=3.1,
                float_millions=22.0,
                rationale="Small float name gapping on imaginary news with strong relative volume.",
            ),
            ScannerCandidate(
                symbol="XYZ",
                price=47.8,
                gap_percent=5.2,
                rvol=2.4,
                float_millions=150.0,
                rationale="Mid-cap showing moderate gap with sustained liquidity for teaching entry sizing.",
            ),
            ScannerCandidate(
                symbol="LMN",
                price=6.75,
                gap_percent=12.0,
                rvol=4.8,
                float_millions=18.5,
                rationale="Low float ticker with double-digit gap and elevated relative volume — classic momentum demo.",
            ),
            ScannerCandidate(
                symbol="QRS",
                price=83.4,
                gap_percent=3.1,
                rvol=1.6,
                float_millions=320.0,
                rationale="Large-cap grinder with modest gap and steady rVol to illustrate higher-float behavior.",
            ),
        ]
        for candidate in candidates:
            print(
                f"[SCAN] Candidate {candidate.symbol}: gap={candidate.gap_percent}% "
                f"rVol={candidate.rvol} float={candidate.float_millions}M — {candidate.rationale}"
            )
        print("[SCAN] Returning static candidate list for downstream teaching modules")
        return candidates
