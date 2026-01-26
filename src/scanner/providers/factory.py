from __future__ import annotations

import logging
import time

from src.config.config_resolver import get_config
from src.config.runtime_config import RunMode, get_run_mode
from .base import ProviderConnectionError, ScannerDataProvider
from .ibkr_provider import IbkrScannerProvider
from .mock_provider import MockScannerProvider


def _source_mode() -> str:
    return str(get_config("SCANNER_DATA_SOURCE"))


def _connect_with_retry(
    provider: IbkrScannerProvider,
    *,
    attempts: int = 3,
    backoff_seconds: float = 0.5,
) -> None:
    last_error: ProviderConnectionError | None = None
    for attempt in range(1, attempts + 1):
        try:
            provider.connect()
            return
        except ProviderConnectionError as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(backoff_seconds)
    if last_error is not None:
        raise last_error


def build_provider() -> ScannerDataProvider:
    mode = _source_mode()
    run_mode = get_run_mode()
    fallback_enabled = bool(get_config("IBKR_FALLBACK_ENABLED"))
    if mode == "MOCK":
        return MockScannerProvider()
    if mode == "IBKR":
        provider = IbkrScannerProvider()
        try:
            _connect_with_retry(provider)
            return provider
        except ProviderConnectionError:
            if run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}:
                raise
            if run_mode == RunMode.SIM and fallback_enabled:
                logging.getLogger(__name__).warning(
                    "[SCAN][FALLBACK] IBKR unavailable — switching to MOCK provider"
                )
                return MockScannerProvider()
            raise
    if mode == "AUTO":
        if run_mode == RunMode.SIM:
            return MockScannerProvider()
        provider = IbkrScannerProvider()
        try:
            _connect_with_retry(provider)
            return provider
        except ProviderConnectionError as exc:
            if run_mode in {RunMode.LIVE, RunMode.LIVE_READ_ONLY, RunMode.LIVE_MICRO}:
                raise
            if run_mode == RunMode.SIM and fallback_enabled:
                logging.getLogger(__name__).warning(
                    "[SCAN][FALLBACK] IBKR unavailable — switching to MOCK provider reason=%s",
                    exc,
                )
                return MockScannerProvider()
            raise
    raise ValueError(f"Unsupported SCANNER_DATA_SOURCE={mode}")
