from __future__ import annotations

import logging

from src.config.config_resolver import get_config
from src.config.runtime_config import RunMode, get_run_mode
from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionManager
from .base import ProviderConnectionError, ScannerDataProvider
from .ibkr_provider import IbkrScannerProvider
from src.ibkr.market_data_client import MarketDataClient
from .mock_provider import MockScannerProvider


def _source_mode() -> str:
    return str(get_config("SCANNER_DATA_SOURCE"))


def build_provider(
    *,
    market_data_client: MarketDataClient | None = None,
    connection_manager: IbkrConnectionManager | None = None,
) -> ScannerDataProvider:
    mode = _source_mode()
    run_mode = get_run_mode()
    if mode == "MOCK":
        return MockScannerProvider()
    if mode == "IBKR":
        provider = IbkrScannerProvider(
            connection_manager=connection_manager,
            market_data_client=market_data_client,
        )
        provider.connect()
        return provider
    if mode == "AUTO":
        if run_mode in {RunMode.SIM, RunMode.PAPER}:
            if run_mode == RunMode.PAPER:
                logging.getLogger(__name__).info(
                    "[SCAN][PAPER] PAPER mode selects MOCK scanner provider (no IBKR connect attempt)."
                )
            return MockScannerProvider()
        provider = IbkrScannerProvider(
            connection_manager=connection_manager,
            market_data_client=market_data_client,
        )
        provider.connect()
        return provider
    raise ValueError(f"Unsupported SCANNER_DATA_SOURCE={mode}")
