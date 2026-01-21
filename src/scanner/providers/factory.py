from __future__ import annotations

import logging

from src.config.config_resolver import get_config
from src.config.runtime_config import RunMode, get_run_mode
from .base import ProviderConnectionError, ScannerDataProvider
from .ibkr_provider import IbkrScannerProvider
from .mock_provider import MockScannerProvider


def _source_mode() -> str:
    return str(get_config("SCANNER_DATA_SOURCE"))


def build_provider() -> ScannerDataProvider:
    mode = _source_mode()
    run_mode = get_run_mode()
    if mode == "MOCK":
        return MockScannerProvider()
    if mode == "IBKR":
        provider = IbkrScannerProvider()
        provider.connect()
        return provider
    if mode == "AUTO":
        if run_mode == RunMode.SIM:
            return MockScannerProvider()
        provider = IbkrScannerProvider()
        try:
            provider.connect()
            return provider
        except ProviderConnectionError as exc:
            logging.getLogger(__name__).warning(
                "[SCAN][FALLBACK] IBKR unavailable — switching to MOCK provider reason=%s",
                exc,
            )
            return MockScannerProvider()
    raise ValueError(f"Unsupported SCANNER_DATA_SOURCE={mode}")
