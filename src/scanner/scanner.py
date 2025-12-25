"""
Scanner module skeleton responsible for producing ranked market candidates.
"""

from typing import List

from models.data_models import ScannerResult


class Scanner:
    """Skeleton scanner that returns empty results with instructional logging."""

    def __init__(self) -> None:
        print("[BOOT] Scanner instantiated — skeleton only")

    def run_scan_cycle(self) -> List[ScannerResult]:
        """Run a scan cycle placeholder and return an empty list."""

        print("[SCAN] Skeleton scanner invoked — no logic implemented yet")
        return []
