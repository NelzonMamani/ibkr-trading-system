from __future__ import annotations

import os

from .base import ProviderConnectionError, ScannerDataProvider
from .ibkr_provider import IbkrScannerProvider
from .mock_provider import MockScannerProvider


def _source_mode() -> str:
    return (os.environ.get("SCANNER_DATA_SOURCE") or "AUTO").strip().upper()


def build_provider() -> ScannerDataProvider:
    mode = _source_mode()
    if mode == "MOCK":
        return MockScannerProvider()
    if mode == "IBKR":
        provider = IbkrScannerProvider()
        provider.connect()
        return provider
    if mode == "AUTO":
        provider = IbkrScannerProvider()
        try:
            provider.connect()
            return provider
        except ProviderConnectionError as exc:
            print(
                "[SCAN][FALLBACK] IBKR unavailable — switching to MOCK provider "
                f"reason={exc}"
            )
            return MockScannerProvider()
    raise ValueError(f"Unsupported SCANNER_DATA_SOURCE={mode}")
