from __future__ import annotations

import logging

from src.config.config_resolver import get_config
from src.config.runtime_config import RunMode, get_run_mode
from .base import ProviderConnectionError, ScannerDataProvider
from .ibkr_provider import IbkrScannerProvider
from src.ibkr.market_data_client import MarketDataClient
from .mock_provider import MockScannerProvider


def _source_mode() -> str:
    return str(get_config("SCANNER_DATA_SOURCE"))


def build_provider(
    *,
    market_data_client: MarketDataClient | None = None,
) -> ScannerDataProvider:
    mode = _source_mode()
    run_mode = get_run_mode()
    fallback_enabled = bool(get_config("IBKR_FALLBACK_ENABLED"))
    if mode == "MOCK":
        return MockScannerProvider()
    if mode == "IBKR":
        provider = IbkrScannerProvider(market_data_client=market_data_client)
        provider.connect()
        return provider
    if mode == "AUTO":
        if run_mode == RunMode.SIM:
            return MockScannerProvider()
        provider = IbkrScannerProvider(market_data_client=market_data_client)
        try:
            provider.connect()
            return provider
        except ProviderConnectionError as exc:
            if run_mode in {
                RunMode.LIVE,
                RunMode.READ_ONLY,
            }:
                raise
            if run_mode == RunMode.PAPER and not fallback_enabled:
                raise
            logging.getLogger(__name__).warning(
                "[SCAN][FALLBACK] IBKR unavailable — switching to MOCK provider reason=%s",
                exc,
            )
            return MockScannerProvider()
    raise ValueError(f"Unsupported SCANNER_DATA_SOURCE={mode}")
