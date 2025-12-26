"""
Scanner module skeleton for illustrating how market candidates could be produced.

Phase 3: Skeleton status only — this module contains placeholders for teaching.
No real scanning logic is implemented; outputs are empty for demonstration.
"""

from typing import List

from src.models.data_models import ScannerCandidate


class Scanner:
    """Minimal scanner placeholder with instructional logging."""

    def __init__(self) -> None:
        print("[BOOT] Scanner instantiated — phase 4 teaching placeholder (static outputs)")

    def run_scan_cycle(self) -> List[ScannerCandidate]:
        """
        Demonstrate how a scan cycle would be invoked in a real system.

        Returns a deterministic list of hard-coded teaching candidates to let
        downstream modules be exercised without touching real markets.
        """

        print("[SCAN] Teaching scan started — using static, fake symbols only")
        print(
            "[SCAN] These candidates are simulated for instruction; no live data, "
            "no randomness, no external calls"
        )

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
