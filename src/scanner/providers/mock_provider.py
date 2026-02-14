from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.config.config_resolver import get_config
from .base import IntradayStats, QuoteData, ScannerDataProvider


_MOCK_SYMBOL_FIXTURES: dict[str, dict[str, float | int]] = {
    "MCKA": {"prev_close": 4.00, "last": 5.20, "gap_pct": 30.0, "rvol": 6.5, "avg_volume": 450_000, "float_shares": 12_000_000},
    "MCKB": {"prev_close": 6.20, "last": 7.56, "gap_pct": 21.9, "rvol": 5.8, "avg_volume": 900_000, "float_shares": 28_000_000},
    "MCKC": {"prev_close": 8.40, "last": 9.83, "gap_pct": 17.0, "rvol": 5.2, "avg_volume": 1_100_000, "float_shares": 36_000_000},
    "MCKD": {"prev_close": 10.00, "last": 11.40, "gap_pct": 14.0, "rvol": 4.7, "avg_volume": 1_250_000, "float_shares": 42_000_000},
    "MCKE": {"prev_close": 12.50, "last": 13.93, "gap_pct": 11.4, "rvol": 4.1, "avg_volume": 1_500_000, "float_shares": 55_000_000},
    "MCKF": {"prev_close": 14.20, "last": 15.48, "gap_pct": 9.0, "rvol": 3.8, "avg_volume": 1_700_000, "float_shares": 67_000_000},
    "MCKG": {"prev_close": 16.00, "last": 17.36, "gap_pct": 8.5, "rvol": 3.4, "avg_volume": 1_850_000, "float_shares": 75_000_000},
    "MCKH": {"prev_close": 18.00, "last": 19.08, "gap_pct": 6.0, "rvol": 3.0, "avg_volume": 2_100_000, "float_shares": 88_000_000},
    "MCKI": {"prev_close": 20.00, "last": 21.00, "gap_pct": 5.0, "rvol": 2.6, "avg_volume": 2_400_000, "float_shares": 95_000_000},
    "MCKJ": {"prev_close": 22.00, "last": 22.88, "gap_pct": 4.0, "rvol": 2.2, "avg_volume": 2_700_000, "float_shares": 110_000_000},
}


def _load_mock_symbols(path: Path, fallback: list[str]) -> list[str]:
    if not path.exists():
        return fallback
    symbols: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            symbol = line.strip().upper()
            if not symbol or symbol.startswith("#"):
                continue
            symbols.append(symbol)
    except Exception:
        return fallback
    return symbols or fallback


def _load_float_cache(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


class MockScannerProvider(ScannerDataProvider):
    source_name = "MOCK"

    def __init__(self, symbols: Optional[list[str]] = None, seed: Optional[int] = None) -> None:
        self.seed = seed if seed is not None else int(get_config("SCANNER_MOCK_SEED"))
        default_file = Path(__file__).resolve().parents[1] / "mock_universe.txt"
        symbols_file = Path(get_config("SCANNER_MOCK_SYMBOLS_FILE") or str(default_file))
        fallback = list(_MOCK_SYMBOL_FIXTURES.keys())
        loaded_symbols = symbols or _load_mock_symbols(symbols_file, fallback)
        self.symbols = [symbol for symbol in loaded_symbols if symbol in _MOCK_SYMBOL_FIXTURES] or fallback
        float_cache_path = Path(get_config("SCANNER_FLOAT_CACHE_FILE"))
        self.float_cache = _load_float_cache(float_cache_path)

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def _fixture(self, symbol: str) -> dict[str, float | int]:
        return _MOCK_SYMBOL_FIXTURES.get(symbol, _MOCK_SYMBOL_FIXTURES["MCKJ"])

    def get_top_gainers(self, limit: int, request=None) -> list[str]:
        return self.symbols[:limit]

    def get_quote(self, symbol: str) -> QuoteData:
        fixture = self._fixture(symbol)
        prev_close = float(fixture["prev_close"])
        last = float(fixture["last"])
        pct_change = round(((last - prev_close) / prev_close) * 100.0, 2)
        open_price = round(prev_close * (1.0 + float(fixture["gap_pct"]) / 100.0), 2)
        bid = round(last - 0.01, 2)
        ask = round(last + 0.01, 2)
        high = round(max(last, open_price) * 1.02, 2)
        low = round(min(last, open_price) * 0.98, 2)
        vwap = round((last + open_price + high + low) / 4.0, 2)
        avg_volume = int(fixture["avg_volume"])
        rvol = float(fixture["rvol"])
        volume = int(avg_volume * rvol)
        return QuoteData(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            vwap=vwap,
            open=open_price,
            high=high,
            low=low,
            close=prev_close,
            change_percent=pct_change,
            volume=volume,
            timestamp_utc=None,
            data_quality_flags=(),
        )

    def get_prev_close(self, symbol: str) -> Optional[float]:
        return float(self._fixture(symbol)["prev_close"])

    def get_intraday_stats(self, symbol: str) -> IntradayStats:
        fixture = self._fixture(symbol)
        avg_volume = int(fixture["avg_volume"])
        rvol = float(fixture["rvol"])
        current_volume = int(avg_volume * rvol)
        return IntradayStats(
            current_intraday_volume=current_volume,
            current_volume_source_label="MOCK",
            average_daily_volume_20d=avg_volume,
            average_daily_volume_window_days=20,
            relative_volume=round(rvol, 2),
            relative_volume_category="HIGH" if rvol >= 3 else "NORMAL",
            volume_velocity_5m=max(5_000, int(current_volume * 0.04)),
            volume_velocity_15m=max(15_000, int(current_volume * 0.12)),
            volume_data_quality_flag=None,
        )

    def get_float(self, symbol: str) -> Optional[int]:
        cached = self.float_cache.get(symbol)
        try:
            if cached is not None:
                return int(cached)
        except Exception:
            pass
        return int(self._fixture(symbol)["float_shares"])
